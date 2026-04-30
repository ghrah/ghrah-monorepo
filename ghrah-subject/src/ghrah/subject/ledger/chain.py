"""ActionChain 分类账：追加写入的不可变账本。

接收 Core 的 ACTION_CHAIN_UPDATED 事件（经 Gateway），持久化节点数据到 SQLite，
维护内存中的 ActionChain 索引用于快速查询，支持跨 Agent DAG 遍历。

关键设计：
- 追加写入：只允许 append_node，不允许修改或删除已写入的节点
- SubjectPersistenceService 是唯一的持久化入口
- 内存缓存 ActionChain + _node_index 加速查询
- 启动时从数据库恢复缓存
- 持久化失败时抛出异常，不更新内存状态
- 所有写操作通过 asyncio.Lock 保护并发安全
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from ghrah.context.chain import ActionChain
from ghrah.context.node import ContextNode
from ghrah.context.persistence.serialization import (
    deserialize_node,
    serialize_node,
)
from ghrah.subject.ledger.models import ChainMeta, DAGEntry, LedgerNode
from ghrah.subject.persistence.service import SubjectPersistenceService

logger = logging.getLogger(__name__)

__all__ = ["ActionChainLedger"]


class PersistenceError(Exception):
    pass


class ActionChainLedger:
    def __init__(self, persistence: SubjectPersistenceService) -> None:
        self._persistence = persistence
        self._chains: dict[str, ActionChain] = {}
        self._node_index: dict[str, ContextNode] = {}
        self._chain_metas: dict[str, ChainMeta] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            result = await self._persistence.handle_command("persist_list_agents", {})
        except Exception:
            logger.warning("Failed to load agents during ledger start")
            return

        if not result.get("success", False):
            logger.warning("Failed to list agents: %s", result.get("error"))
            return

        agent_names: list[str] = result.get("data", {}).get("agents", [])
        for agent_name in agent_names:
            await self._load_agent_chain(agent_name)

    async def _load_agent_chain(self, agent_name: str) -> None:
        chain_result = await self._persistence.handle_command(
            "persist_load_chain", {"agent_name": agent_name}
        )
        if not chain_result.get("success", False):
            logger.warning("Failed to load chain for agent %s", agent_name)
            return

        nodes_data: list[dict[str, Any]] = chain_result.get("data", {}).get("nodes", [])
        if not nodes_data:
            return

        nodes = [deserialize_node(nd) for nd in nodes_data]
        chain = ActionChain.rebuild_from_nodes(agent_name, nodes)
        for node in nodes:
            self._node_index[node.id] = node

        self._chains[agent_name] = chain

        meta_result = await self._persistence.handle_command(
            "persist_load_chain_meta", {"agent_name": agent_name}
        )
        if meta_result.get("success", False) and meta_result.get("data") is not None:
            data = meta_result["data"]
            self._chain_metas[agent_name] = ChainMeta(
                agent_name=agent_name,
                branches=data.get("branches", {}),
                current_state=data.get("current_state", {}),
                active_session_id=data.get("active_session_id", ""),
            )
        else:
            self._chain_metas[agent_name] = ChainMeta(
                agent_name=agent_name,
                branches=dict(chain.branches),
            )

        logger.info("Loaded chain for agent %s (%d nodes)", agent_name, chain.node_count)

    async def stop(self) -> None:
        logger.info("ActionChainLedger stopped")

    async def append_node(self, agent_name: str, node_data: dict[str, Any]) -> ContextNode:
        node = deserialize_node(node_data)

        result = await self._persistence.handle_command(
            "persist_save_node", {"node": node_data}
        )
        if not result.get("success", False):
            raise PersistenceError(
                f"Failed to persist node {node.id}: {result.get('error', 'unknown')}"
            )

        async with self._lock:
            if agent_name not in self._chains:
                chain = ActionChain(agent_name)
                chain.ingest_node(node)
                self._chains[agent_name] = chain
            else:
                self._chains[agent_name].ingest_node(node)

            self._node_index[node.id] = node

        logger.info(
            "Appended node %s to chain %s (iteration %d)",
            node.id,
            agent_name,
            node.iteration,
        )
        return node

    async def update_chain_meta(
        self,
        agent_name: str,
        branches: dict[str, str],
        current_state: dict[str, Any],
        active_session_id: str = "",
    ) -> None:
        result = await self._persistence.handle_command(
            "persist_save_chain_meta",
            {
                "agent_name": agent_name,
                "branches": branches,
                "current_state": current_state,
                "active_session_id": active_session_id,
            },
        )
        if not result.get("success", False):
            raise PersistenceError(
                f"Failed to persist chain meta for {agent_name}: "
                f"{result.get('error', 'unknown')}"
            )

        async with self._lock:
            self._chain_metas[agent_name] = ChainMeta(
                agent_name=agent_name,
                branches=branches,
                current_state=current_state,
                active_session_id=active_session_id,
            )

            if agent_name in self._chains:
                chain = self._chains[agent_name]
                for branch_name, head_id in branches.items():
                    chain.update_branch(branch_name, head_id)

    def get_node(self, node_id: str) -> ContextNode | None:
        return self._node_index.get(node_id)

    def get_chain(self, agent_name: str) -> ActionChain | None:
        return self._chains.get(agent_name)

    def get_chain_history(
        self, agent_name: str, branch: str = "main", limit: int = -1
    ) -> list[ContextNode]:
        chain = self._chains.get(agent_name)
        if chain is None:
            return []
        return chain.get_history(branch, limit)  # type: ignore[no-any-return]

    def get_branch_head(
        self, agent_name: str, branch: str = "main"
    ) -> ContextNode | None:
        chain = self._chains.get(agent_name)
        if chain is None:
            return None
        return chain.get_branch_head(branch)

    def get_chain_meta(self, agent_name: str) -> ChainMeta | None:
        return self._chain_metas.get(agent_name)

    def traverse_dag(
        self, agent_names: list[str] | None = None
    ) -> list[DAGEntry]:
        children_map: dict[str, list[str]] = {}
        for node_id, node in self._node_index.items():
            if node.parent_id is not None:
                children_map.setdefault(node.parent_id, []).append(node_id)

        target_agents = agent_names if agent_names is not None else list(self._chains.keys())
        entries: list[DAGEntry] = []

        seen: set[str] = set()

        for agent_name in target_agents:
            chain = self._chains.get(agent_name)
            if chain is None:
                continue

            for node in chain.get_history("main"):
                if node.parent_id is None:
                    self._traverse_bfs(node.id, children_map, 0, seen, entries)
                    break

        return entries

    def _traverse_bfs(
        self,
        start_id: str,
        children_map: dict[str, list[str]],
        start_depth: int,
        seen: set[str],
        entries: list[DAGEntry],
    ) -> None:
        queue: deque[tuple[str, int]] = deque([(start_id, start_depth)])
        while queue:
            node_id, depth = queue.popleft()
            if node_id in seen:
                continue
            seen.add(node_id)

            node = self._node_index.get(node_id)
            if node is None:
                continue

            serialized = serialize_node(node)
            ledger_node = LedgerNode.model_validate(serialized)
            children = children_map.get(node_id, [])
            entries.append(DAGEntry(node=ledger_node, children=children, depth=depth))

            for child_id in children:
                if child_id not in seen:
                    queue.append((child_id, depth + 1))

    def list_agents(self) -> list[str]:
        return list(self._chains.keys())

    @property
    def node_count(self) -> int:
        return len(self._node_index)
