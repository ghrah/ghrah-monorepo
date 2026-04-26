from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from ghrah.context.node import ContextNode

from ghrah.subject.ledger.chain import ActionChainLedger, PersistenceError
from ghrah.subject.ledger.models import ChainMeta, DAGEntry, LedgerNode


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


def _node_to_payload(node: ContextNode) -> dict[str, Any]:
    from ghrah.context.persistence.serialization import serialize_node

    return serialize_node(node)


class TestLedgerNode:
    def test_basic_creation(self) -> None:
        node = LedgerNode(
            id="abc123",
            agent_name="agent1",
            iteration=1,
            ability_names=["read_file"],
        )
        assert node.id == "abc123"
        assert node.agent_name == "agent1"
        assert node.iteration == 1
        assert node.ability_names == ["read_file"]
        assert node.branch_name == "main"
        assert node.parent_id is None
        assert node.is_snapshot is False

    def test_from_context_node(self) -> None:
        ctx_node = _make_node(iteration=3, ability_names=["read_file", "write_file"])
        ledger_node = LedgerNode.from_context_node(ctx_node)
        assert ledger_node.id == ctx_node.id
        assert ledger_node.agent_name == ctx_node.agent_name
        assert ledger_node.iteration == ctx_node.iteration
        assert ledger_node.ability_names == ["read_file", "write_file"]
        assert ledger_node.branch_name == ctx_node.branch_name

    def test_to_context_node(self) -> None:
        now = datetime.now(UTC)
        ledger_node = LedgerNode(
            id="test_id",
            parent_id="parent_id",
            agent_name="agent1",
            timestamp=now,
            iteration=2,
            ability_names=["tool"],
        )
        ctx_node = ledger_node.to_context_node()
        assert ctx_node.id == "test_id"
        assert ctx_node.parent_id == "parent_id"
        assert ctx_node.agent_name == "agent1"
        assert ctx_node.iteration == 2
        assert ctx_node.ability_names == ["tool"]

    def test_roundtrip(self) -> None:
        ctx_node = _make_node(iteration=5, ability_names=["a", "b"])
        ledger_node = LedgerNode.from_context_node(ctx_node)
        restored = ledger_node.to_context_node()
        assert restored.id == ctx_node.id
        assert restored.agent_name == ctx_node.agent_name
        assert restored.iteration == ctx_node.iteration
        assert restored.ability_names == ctx_node.ability_names
        assert restored.branch_name == ctx_node.branch_name

    def test_to_dict(self) -> None:
        ledger_node = LedgerNode(id="abc", agent_name="ag1", iteration=0)
        d = ledger_node.to_dict()
        assert isinstance(d, dict)
        assert d["id"] == "abc"
        assert d["agent_name"] == "ag1"

    def test_default_fields(self) -> None:
        node = LedgerNode(id="x")
        assert node.agent_state == {}
        assert node.messages_delta == []
        assert node.messages_snapshot is None
        assert node.action_results == []
        assert node.metadata == {}


class TestChainMeta:
    def test_basic_creation(self) -> None:
        meta = ChainMeta(
            agent_name="agent1",
            branches={"main": "head_1"},
            current_state={"status": "running"},
        )
        assert meta.agent_name == "agent1"
        assert meta.branches == {"main": "head_1"}
        assert meta.current_state == {"status": "running"}

    def test_default_branches(self) -> None:
        meta = ChainMeta(agent_name="agent1")
        assert meta.branches == {}
        assert meta.current_state == {}


class TestDAGEntry:
    def test_basic_creation(self) -> None:
        node = LedgerNode(id="n1", agent_name="ag1", iteration=0)
        entry = DAGEntry(node=node, children=["n2", "n3"], depth=0)
        assert entry.node.id == "n1"
        assert entry.children == ["n2", "n3"]
        assert entry.depth == 0

    def test_default_children(self) -> None:
        node = LedgerNode(id="n1")
        entry = DAGEntry(node=node)
        assert entry.children == []
        assert entry.depth == 0


def _make_mock_persistence() -> AsyncMock:
    mock = AsyncMock(spec=["handle_command"])
    mock.handle_command = AsyncMock()
    return mock


class TestActionChainLedger:
    async def test_append_node_creates_chain(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)
        node = _make_node(agent_name="agent1", iteration=0)
        result = await ledger.append_node("agent1", _node_to_payload(node))

        assert result.id == node.id
        assert result.agent_name == "agent1"
        assert "agent1" in ledger.list_agents()

    async def test_append_node_persists(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)
        node = _make_node(agent_name="agent1", iteration=0)
        await ledger.append_node("agent1", _node_to_payload(node))

        mock_persist.handle_command.assert_called_once()
        call_args = mock_persist.handle_command.call_args
        assert call_args[0][0] == "persist_save_node"

    async def test_append_node_updates_index(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)
        node = _make_node(agent_name="agent1", iteration=0)
        await ledger.append_node("agent1", _node_to_payload(node))

        assert ledger.get_node(node.id) is not None
        assert ledger.get_node(node.id).agent_name == "agent1"

    async def test_append_multiple_nodes(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root = ContextNode.create_root(agent_name="agent1")
        await ledger.append_node("agent1", _node_to_payload(root))

        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await ledger.append_node("agent1", _node_to_payload(child))

        assert ledger.get_node(child.id) is not None
        assert ledger.node_count == 2

    async def test_get_node_not_found(self) -> None:
        mock_persist = _make_mock_persistence()
        ledger = ActionChainLedger(mock_persist)

        assert ledger.get_node("nonexistent") is None

    async def test_get_chain_history(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await ledger.append_node("agent1", _node_to_payload(child))

        history = ledger.get_chain_history("agent1")
        assert len(history) == 2
        assert history[0].id == root.id
        assert history[1].id == child.id

    async def test_get_chain_history_with_limit(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await ledger.append_node("agent1", _node_to_payload(child))

        history = ledger.get_chain_history("agent1", limit=1)
        assert len(history) == 1
        assert history[0].id == child.id

    async def test_get_branch_head(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        head = ledger.get_branch_head("agent1")
        assert head is not None
        assert head.id == root.id

    async def test_get_branch_head_nonexistent_agent(self) -> None:
        mock_persist = _make_mock_persistence()
        ledger = ActionChainLedger(mock_persist)

        assert ledger.get_branch_head("nonexistent") is None

    async def test_get_chain(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        chain = ledger.get_chain("agent1")
        assert chain is not None
        assert chain.agent_name == "agent1"

    async def test_get_chain_nonexistent(self) -> None:
        mock_persist = _make_mock_persistence()
        ledger = ActionChainLedger(mock_persist)

        assert ledger.get_chain("nonexistent") is None

    async def test_get_chain_meta_default(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)
        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        meta = ledger.get_chain_meta("agent1")
        assert meta is None

    async def test_update_chain_meta(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)
        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        await ledger.update_chain_meta(
            "agent1",
            branches={"main": root.id},
            current_state={"status": "running"},
        )

        mock_persist.handle_command.assert_called()
        save_calls = [
            c for c in mock_persist.handle_command.call_args_list
            if c[0][0] == "persist_save_chain_meta"
        ]
        assert len(save_calls) == 1

        meta = ledger.get_chain_meta("agent1")
        assert meta is not None
        assert meta.branches == {"main": root.id}
        assert meta.current_state == {"status": "running"}

    async def test_traverse_dag_single_agent(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await ledger.append_node("agent1", _node_to_payload(child))

        entries = ledger.traverse_dag()
        assert len(entries) == 2
        root_entry = next(e for e in entries if e.node.id == root.id)
        child_entry = next(e for e in entries if e.node.id == child.id)
        assert root_entry.children == [child.id]
        assert child_entry.children == []
        assert root_entry.depth == 0
        assert child_entry.depth == 1

    async def test_traverse_dag_multi_agent(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root_a = ContextNode.create_root(agent_name="agent_a", messages=[])
        await ledger.append_node("agent_a", _node_to_payload(root_a))

        root_b = ContextNode.create_root(agent_name="agent_b", messages=[])
        await ledger.append_node("agent_b", _node_to_payload(root_b))

        entries = ledger.traverse_dag()
        assert len(entries) == 2

        entries_a = ledger.traverse_dag(agent_names=["agent_a"])
        assert len(entries_a) == 1
        assert entries_a[0].node.agent_name == "agent_a"

    async def test_list_agents(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)

        root_a = ContextNode.create_root(agent_name="agent_a", messages=[])
        await ledger.append_node("agent_a", _node_to_payload(root_a))

        root_b = ContextNode.create_root(agent_name="agent_b", messages=[])
        await ledger.append_node("agent_b", _node_to_payload(root_b))

        agents = ledger.list_agents()
        assert set(agents) == {"agent_a", "agent_b"}

    async def test_node_count(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)
        assert ledger.node_count == 0

        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))
        assert ledger.node_count == 1

        child = ContextNode(
            parent_id=root.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        await ledger.append_node("agent1", _node_to_payload(child))
        assert ledger.node_count == 2

    async def test_start_restores_from_db(self) -> None:
        mock_persist = _make_mock_persistence()

        root_node = ContextNode.create_root(agent_name="agent1", messages=[])
        root_data = _node_to_payload(root_node)

        child_node = ContextNode(
            parent_id=root_node.id,
            agent_name="agent1",
            iteration=1,
            ability_names=["tool_a"],
        )
        child_data = _node_to_payload(child_node)

        mock_persist.handle_command.side_effect = [
            {"success": True, "data": {"agents": ["agent1"]}},
            {"success": True, "data": {"nodes": [root_data, child_data]}},
            {
                "success": True,
                "data": {
                    "branches": {"main": child_node.id},
                    "current_state": {"status": "idle"},
                },
            },
        ]

        ledger = ActionChainLedger(mock_persist)
        await ledger.start()

        assert "agent1" in ledger.list_agents()
        assert ledger.get_node(root_node.id) is not None
        assert ledger.get_node(child_node.id) is not None

        meta = ledger.get_chain_meta("agent1")
        assert meta is not None
        assert meta.branches == {"main": child_node.id}

    async def test_start_handles_empty_db(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {
            "success": True,
            "data": {"agents": []},
        }

        ledger = ActionChainLedger(mock_persist)
        await ledger.start()

        assert ledger.list_agents() == []

    async def test_start_handles_failure(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {
            "success": False,
            "error": "db not started",
        }

        ledger = ActionChainLedger(mock_persist)
        await ledger.start()

        assert ledger.list_agents() == []

    async def test_stop(self) -> None:
        mock_persist = _make_mock_persistence()
        ledger = ActionChainLedger(mock_persist)
        await ledger.stop()

    async def test_append_node_persistence_failure_raises(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {
            "success": False,
            "error": "disk full",
        }

        ledger = ActionChainLedger(mock_persist)
        node = _make_node(agent_name="agent1", iteration=0)

        with pytest.raises(PersistenceError, match="Failed to persist node"):
            await ledger.append_node("agent1", _node_to_payload(node))

        assert ledger.node_count == 0
        assert "agent1" not in ledger.list_agents()

    async def test_update_chain_meta_persistence_failure_raises(self) -> None:
        mock_persist = _make_mock_persistence()
        mock_persist.handle_command.return_value = {"success": True}

        ledger = ActionChainLedger(mock_persist)
        root = ContextNode.create_root(agent_name="agent1", messages=[])
        await ledger.append_node("agent1", _node_to_payload(root))

        mock_persist.handle_command.return_value = {
            "success": False,
            "error": "write failed",
        }

        with pytest.raises(PersistenceError, match="Failed to persist chain meta"):
            await ledger.update_chain_meta(
                "agent1",
                branches={"main": root.id},
                current_state={"status": "running"},
            )

        meta = ledger.get_chain_meta("agent1")
        assert meta is None
