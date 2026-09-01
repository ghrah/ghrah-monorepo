# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActionChainLedger（读侧直连 Core sqlite）测试。

聚合裁决 D-C：真相源 = Core ``ContextManager`` 的 sqlite；本文件用真实
``SqliteBackend`` 写入节点（模拟 Core 侧 agent 链落库），断言 ledger
读侧投影（同文件 WAL 双连接）按需查询正确。
"""

from __future__ import annotations

from pathlib import Path

from ghrah.context.node import ContextNode
from ghrah.context.persistence import serialize_node
from ghrah.context.persistence.sqlite_backend import (  # type: ignore[import-untyped]
    SqliteBackend,
)

from ghrah.subject.ledger.chain import ActionChainLedger
from ghrah.subject.ledger.models import ChainMeta, DAGEntry, LedgerNode

# ----------------------------------------------------------------
# 测试辅助
# ----------------------------------------------------------------


def _make_node(
    agent_name: str = "test_agent",
    iteration: int = 0,
    parent_id: str | None = None,
    ability_names: list[str] | None = None,
    branch_name: str = "main",
    node_id: str | None = None,
) -> ContextNode:
    if ability_names is None:
        ability_names = ["init"] if iteration == 0 else ["tool_call"]
    return ContextNode(
        id=node_id or f"node_{iteration}",
        parent_id=parent_id,
        agent_name=agent_name,
        iteration=iteration,
        ability_names=ability_names,
        branch_name=branch_name,
    )


async def _seed_backend(db_path: Path, nodes: list[ContextNode]) -> SqliteBackend:
    """模拟 Core 侧写入（同一 SqliteBackend API，真相源角色）。"""
    backend = SqliteBackend(db_path=db_path)
    await backend.connect()
    for node in nodes:
        await backend.save_node(node)
    await backend.close()
    return backend


# ----------------------------------------------------------------
# models（纯序列化契约，行为不变，保留原断言面）
# ----------------------------------------------------------------


class TestLedgerNode:
    def test_serialize_roundtrip(self) -> None:
        node = _make_node(iteration=3, parent_id="node_2")
        serialized = serialize_node(node)
        ledger_node = LedgerNode.model_validate(serialized)
        assert ledger_node.id == node.id
        assert ledger_node.agent_name == node.agent_name
        assert ledger_node.iteration == 3
        assert ledger_node.parent_id == "node_2"


class TestChainMeta:
    def test_fields(self) -> None:
        meta = ChainMeta(
            agent_name="a",
            branches={"main": "node_1"},
            current_state={"k": 1},
            active_session_id="s-1",
        )
        assert meta.agent_name == "a"
        assert meta.branches == {"main": "node_1"}
        assert meta.active_session_id == "s-1"


class TestDAGEntry:
    def test_fields(self) -> None:
        node = LedgerNode.model_validate(serialize_node(_make_node()))
        entry = DAGEntry(node=node, children=["c1"], depth=2)
        assert entry.node is node
        assert entry.children == ["c1"]
        assert entry.depth == 2


# ----------------------------------------------------------------
# 读侧投影（真实 SqliteBackend 双连接）
# ----------------------------------------------------------------


class TestReadSideProjection:
    async def test_chain_history_reads_core_written_nodes(self, tmp_path: Path) -> None:
        db = tmp_path / "ghrah.db"
        root = ContextNode.create_root(agent_name="agent1", messages=[])
        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await _seed_backend(db, [root, child])

        ledger = ActionChainLedger(db)
        await ledger.start()
        try:
            history = await ledger.get_chain_history("agent1")
            assert [n.id for n in history] == [root.id, child.id]

            assert await ledger.get_node(child.id) is not None
            assert (await ledger.get_node(child.id)).agent_name == "agent1"  # type: ignore[union-attr]
        finally:
            await ledger.stop()

    async def test_chain_history_limit(self, tmp_path: Path) -> None:
        db = tmp_path / "ghrah.db"
        root = ContextNode.create_root(agent_name="agent1", messages=[])
        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await _seed_backend(db, [root, child])

        ledger = ActionChainLedger(db)
        await ledger.start()
        try:
            history = await ledger.get_chain_history("agent1", limit=1)
            assert len(history) == 1
        finally:
            await ledger.stop()

    async def test_unknown_agent_returns_empty(self, tmp_path: Path) -> None:
        ledger = ActionChainLedger(tmp_path / "ghrah.db")
        await ledger.start()
        try:
            assert await ledger.get_chain_history("nobody") == []
            assert await ledger.get_chain_meta("nobody") is None
            assert await ledger.get_node("nonexistent") is None
        finally:
            await ledger.stop()

    async def test_chain_meta_and_branch_head(self, tmp_path: Path) -> None:
        db = tmp_path / "ghrah.db"
        root = ContextNode.create_root(agent_name="agent1", messages=[])
        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await _seed_backend(db, [root, child])
        writer = SqliteBackend(db_path=db)
        await writer.connect()
        await writer.save_chain_meta(
            "agent1",
            branches={"main": child.id},
            current_state={"phase": "run"},
            active_session_id="sess-9",
        )
        await writer.close()

        ledger = ActionChainLedger(db)
        await ledger.start()
        try:
            meta = await ledger.get_chain_meta("agent1")
            assert meta is not None
            assert meta.active_session_id == "sess-9"
            assert meta.branches == {"main": child.id}

            head = await ledger.get_branch_head("agent1")
            assert head is not None
            assert head.id == child.id
        finally:
            await ledger.stop()

    async def test_list_agents_and_traverse_dag(self, tmp_path: Path) -> None:
        db = tmp_path / "ghrah.db"
        root_a = ContextNode.create_root(agent_name="agent-a", messages=[])
        child_a = ContextNode(
            parent_id=root_a.id,
            agent_name="agent-a",
            iteration=1,
            ability_names=["tool_a"],
        )
        root_b = ContextNode.create_root(agent_name="agent-b", messages=[])
        await _seed_backend(db, [root_a, child_a, root_b])

        ledger = ActionChainLedger(db)
        await ledger.start()
        try:
            assert sorted(await ledger.list_agents()) == ["agent-a", "agent-b"]
            assert await ledger.node_count() == 3

            entries = await ledger.traverse_dag(["agent-a"])
            assert len(entries) == 2
            assert entries[0].node.id == root_a.id
            assert entries[0].children == [child_a.id]
            assert entries[1].depth == 1
        finally:
            await ledger.stop()

    async def test_start_stop_idempotent(self, tmp_path: Path) -> None:
        ledger = ActionChainLedger(tmp_path / "ghrah.db")
        await ledger.start()
        await ledger.start()  # 幂等
        await ledger.stop()
        await ledger.stop()  # 幂等
