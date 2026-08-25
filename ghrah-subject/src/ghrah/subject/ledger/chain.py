# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActionChain 读侧投影（Core sqlite 直连，只读）。

聚合裁决 D-C：存储真相源 = Core ``ContextManager`` 的 sqlite（per-agent
链/chain_meta/messages 全在 Core 内建 backend）；本模块退化为 ``chain_history``
读命令的薄投影——经 Core ``SqliteBackend`` 的 ``load_chain``/
``load_chain_meta``/``load_node``/``list_agents`` API 按需查询（同一 db
文件的第二个 WAL 连接），不再持有内存全量缓存，也不再写侧落库
（旧事件驱动 ``append_node``/``update_chain_meta`` 面已死，随删）。

DB 路径经 ``SubjectConfig.core_db_path`` 派生（与 registry 构造 CoreUnit
的 persistence_factory 同源，保证读写同一文件）。
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

from ghrah.context.chain import ActionChain  # type: ignore[import-untyped]
from ghrah.context.node import ContextNode  # type: ignore[import-untyped]
from ghrah.context.persistence import serialize_node  # type: ignore[import-untyped]
from ghrah.context.persistence.sqlite_backend import (  # type: ignore[import-untyped]
    SqliteBackend,
)
from ghrah.subject.ledger.models import ChainMeta, DAGEntry, LedgerNode

logger = logging.getLogger(__name__)

__all__ = ["ActionChainLedger"]


class ActionChainLedger:
    """Core sqlite 只读投影（chain_history 命令面）。

    Args:
        db_path: Core sqlite 文件路径（None → SqliteBackend 默认派生）。
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._backend = SqliteBackend(db_path=db_path)
        self._started = False

    @property
    def db_path(self) -> Path:
        return Path(self._backend.db_path)

    async def start(self) -> None:
        """打开只读连接（同文件 WAL 双连接；文件/schema 懒建无妨）。"""
        if self._started:
            return
        await self._backend.connect()
        self._started = True
        logger.info("ActionChainLedger started (read-side, db=%s)", self.db_path)

    async def stop(self) -> None:
        if not self._started:
            return
        await self._backend.close()
        self._started = False
        logger.info("ActionChainLedger stopped")

    # ─── 读 API（按需查询 Core backend） ───

    async def get_node(self, node_id: str) -> ContextNode | None:
        return await self._backend.load_node(node_id)

    async def get_chain_history(
        self, agent_name: str, branch: str = "main", limit: int = -1
    ) -> list[ContextNode]:
        chain = await self._build_chain(agent_name)
        if chain is None:
            return []
        return chain.get_history(branch, limit)  # type: ignore[no-any-return]

    async def get_branch_head(self, agent_name: str, branch: str = "main") -> ContextNode | None:
        chain = await self._build_chain(agent_name)
        if chain is None:
            return None
        return chain.get_branch_head(branch)

    async def get_chain_meta(self, agent_name: str) -> ChainMeta | None:
        loaded = await self._backend.load_chain_meta(agent_name)
        if loaded is None:
            return None
        branches, active_session_id, current_state = loaded
        return ChainMeta(
            agent_name=agent_name,
            branches=branches,
            current_state=current_state,
            active_session_id=active_session_id,
        )

    async def traverse_dag(self, agent_names: list[str] | None = None) -> list[DAGEntry]:
        targets = agent_names if agent_names is not None else await self.list_agents()

        node_index: dict[str, ContextNode] = {}
        for agent_name in targets:
            for node in await self._backend.load_chain(agent_name):
                node_index[node.id] = node

        children_map: dict[str, list[str]] = {}
        for node_id, node in node_index.items():
            if node.parent_id is not None:
                children_map.setdefault(node.parent_id, []).append(node_id)

        entries: list[DAGEntry] = []
        seen: set[str] = set()
        for agent_name in targets:
            chain = await self._build_chain(agent_name)
            if chain is None:
                continue
            for node in chain.get_history("main"):
                if node.parent_id is None:
                    self._traverse_bfs(node.id, node_index, children_map, 0, seen, entries)
                    break
        return entries

    async def list_agents(self) -> list[str]:
        return [str(name) for name in await self._backend.list_agents()]

    async def node_count(self) -> int:
        total = 0
        for agent_name in await self.list_agents():
            total += len(await self._backend.load_chain(agent_name))
        return total

    async def _build_chain(self, agent_name: str) -> ActionChain | None:
        nodes = await self._backend.load_chain(agent_name)
        if not nodes:
            return None
        return ActionChain.rebuild_from_nodes(agent_name, nodes)

    def _traverse_bfs(
        self,
        start_id: str,
        node_index: dict[str, ContextNode],
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

            node = node_index.get(node_id)
            if node is None:
                continue

            serialized = serialize_node(node)
            ledger_node = LedgerNode.model_validate(serialized)
            children = children_map.get(node_id, [])
            entries.append(DAGEntry(node=ledger_node, children=children, depth=depth))

            for child_id in children:
                if child_id not in seen:
                    queue.append((child_id, depth + 1))
