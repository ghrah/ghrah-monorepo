# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""SQLite v2 多 Session checkpoint 与增量写入测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ghrah.chat.factory import ChatMessageFactory
from ghrah.context import ContextManager
from ghrah.context.persistence.sqlite_backend import SqliteBackend


@pytest.mark.asyncio
async def test_sqlite_round_trip_multiple_sessions_and_branches(tmp_path: Path) -> None:
    """SQLite 往返保留多 Root、Branch Head 和激活指针。"""
    backend = SqliteBackend(db_path=tmp_path / "context.db", run_id="run-a")
    await backend.connect()
    cm = ContextManager(
        agent_name="agent",
        persistence=backend,
        message_factory=ChatMessageFactory(),
    )
    first_session_id = cm.active_session_id
    cm.begin_iteration()
    cm.apply_state_changes({"path": "first"})
    cm.commit_iteration(ability_names=["first"])
    second = cm.create_session(initial_state={"path": "second"})
    cm.activate_session(second.session_id)
    retry = cm.create_branch(session_id=second.session_id, name="retry-1")
    cm.activate_branch(second.session_id, retry.branch_id)
    await cm.persist()
    await backend.close()

    restored_backend = SqliteBackend(db_path=tmp_path / "context.db", run_id="run-b")
    await restored_backend.connect()
    restored = ContextManager(
        agent_name="agent",
        persistence=restored_backend,
        message_factory=ChatMessageFactory(),
    )
    await restored.restore("agent")

    assert {session.session_id for session in restored.list_sessions()} == {
        first_session_id,
        second.session_id,
    }
    assert restored.active_session_id == second.session_id
    assert restored.get_active_session().active_branch_id == retry.branch_id
    assert restored.get_current_state() == {"path": "second"}
    await restored_backend.close()


@pytest.mark.asyncio
async def test_sqlite_commits_do_not_delete_existing_nodes(tmp_path: Path) -> None:
    """连续 commit 只增量 INSERT，不得 DELETE 已有节点。"""
    backend = SqliteBackend(db_path=tmp_path / "context.db", run_id="run-a")
    await backend.connect()
    cm = ContextManager(
        agent_name="agent",
        persistence=backend,
        auto_persist=True,
        message_factory=ChatMessageFactory(),
    )
    await cm.wait_for_persist()
    db = await backend._ensure_db()
    await db.executescript(
        """
        CREATE TABLE node_delete_audit (node_id TEXT NOT NULL);
        CREATE TRIGGER audit_node_delete AFTER DELETE ON nodes
        BEGIN
            INSERT INTO node_delete_audit (node_id) VALUES (OLD.id);
        END;
        """
    )

    for index in range(50):
        cm.begin_iteration()
        cm.commit_iteration(ability_names=[f"step-{index}"])
    await cm.wait_for_persist()

    count_cursor = await db.execute("SELECT COUNT(*) AS count FROM nodes")
    delete_cursor = await db.execute("SELECT COUNT(*) AS count FROM node_delete_audit")
    assert (await count_cursor.fetchone())["count"] == 51
    assert (await delete_cursor.fetchone())["count"] == 0
    await backend.close()


@pytest.mark.asyncio
async def test_legacy_sqlite_schema_fails_fast(tmp_path: Path) -> None:
    """无 v2 schema marker 的旧库必须显式重建。"""
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY)")
    connection.commit()
    connection.close()

    backend = SqliteBackend(db_path=path, run_id="run-a")
    await backend.connect()
    with pytest.raises(RuntimeError, match="Legacy context database schema"):
        await backend.load_checkpoint("agent")
    await backend.close()
