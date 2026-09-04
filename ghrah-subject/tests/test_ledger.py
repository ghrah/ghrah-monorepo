# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActionChainLedger v2 多 Session/Branch 读侧测试。"""

from pathlib import Path

from ghrah.context.persistence import ContextChanges
from ghrah.context.persistence.sqlite_backend import SqliteBackend  # type: ignore[import-untyped]
from ghrah.context.session_runtime import SessionRuntime

from ghrah.subject.ledger.chain import ActionChainLedger


async def _seed(db_path: Path, agent_name: str, steps: int = 1) -> SessionRuntime:
    runtime = SessionRuntime.create(agent_name=agent_name)
    for index in range(steps):
        runtime.commit_node(ability_names=[f"tool-{index}"])
    changes = ContextChanges(
        agent_name=agent_name,
        sessions=(runtime.session,),
        branches=tuple(runtime.branches.values()),
        nodes=tuple(runtime.chain.nodes),
        active_session_id=runtime.session.session_id,
    )
    backend = SqliteBackend(db_path=db_path)
    await backend.connect()
    await backend.apply_changes(changes)
    await backend.close()
    return runtime


async def test_history_is_addressed_by_session_and_branch(tmp_path: Path) -> None:
    db = tmp_path / "action.db"
    runtime = await _seed(db, "agent", steps=2)
    branch = runtime.active_branch
    ledger = ActionChainLedger(db)
    await ledger.start()
    try:
        history = await ledger.get_chain_history(
            "agent", runtime.session.session_id, branch.branch_id
        )
        assert [node.id for node in history] == [
            node.id for node in runtime.get_history(branch.branch_id)
        ]
        limited = await ledger.get_chain_history(
            "agent", runtime.session.session_id, branch.branch_id, limit=1
        )
        assert limited == [runtime.active_head]
    finally:
        await ledger.stop()


async def test_unknown_session_returns_empty(tmp_path: Path) -> None:
    db = tmp_path / "action.db"
    runtime = await _seed(db, "agent")
    ledger = ActionChainLedger(db)
    await ledger.start()
    try:
        assert (
            await ledger.get_chain_history("agent", "missing", runtime.active_branch.branch_id)
            == []
        )
        assert await ledger.get_chain_meta("missing-agent") is None
    finally:
        await ledger.stop()


async def test_meta_head_and_dag(tmp_path: Path) -> None:
    db = tmp_path / "action.db"
    runtime = await _seed(db, "agent", steps=2)
    ledger = ActionChainLedger(db)
    await ledger.start()
    try:
        meta = await ledger.get_chain_meta("agent")
        assert meta is not None
        assert meta.active_session_id == runtime.session.session_id
        assert meta.sessions[0]["root_node_id"] == runtime.session.root_node_id
        assert meta.branches[0]["head_node_id"] == runtime.active_head.id
        head = await ledger.get_branch_head(
            "agent", runtime.session.session_id, runtime.active_branch.branch_id
        )
        assert head == runtime.active_head
        assert await ledger.list_agents() == ["agent"]
        assert await ledger.node_count() == 3
        entries = await ledger.traverse_dag(["agent"])
        assert [entry.depth for entry in entries] == [0, 1, 2]
    finally:
        await ledger.stop()


async def test_start_stop_idempotent(tmp_path: Path) -> None:
    ledger = ActionChainLedger(tmp_path / "action.db")
    await ledger.start()
    await ledger.start()
    await ledger.stop()
    await ledger.stop()
