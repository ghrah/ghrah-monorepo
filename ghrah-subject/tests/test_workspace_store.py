# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WorkspaceStore 单测（挂载语义）。

覆盖：
- 持久化往返（upsert/get/get_by_locator/list，含重启重建）；
- 软删（soft_delete 排除、重复返回 False、include_deleted 取回）；
- legacy git 记录 start() 自动 retag 为 plain。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ghrah.subject.workspace import WorkspaceRecord, WorkspaceStore, path_to_locator

# ─── fixtures / helpers ───


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[WorkspaceStore]:
    s = WorkspaceStore(tmp_path / "workspaces.db")
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


def _record(
    *,
    workspace_id: str = "wid-1",
    name: str = "agent-x",
    provider_type: str = "plain",
    subject_id: str = "default",
    locator: str | None = None,
) -> WorkspaceRecord:
    return WorkspaceRecord(
        workspace_id=workspace_id,
        name=name,
        provider_type=provider_type,
        subject_id=subject_id,
        locator=locator or path_to_locator("/abs/agent-x"),
    )


def _now() -> datetime:
    return datetime.now(UTC)


# ─── A. WorkspaceStore 持久化往返 ───


class TestStoreRoundtrip:
    async def test_upsert_and_get(self, store: WorkspaceStore) -> None:
        rec = _record(locator=path_to_locator("/abs/a"))
        await store.upsert(rec)
        got = await store.get("wid-1")
        assert got is not None
        assert got.workspace_id == "wid-1"
        assert got.provider_type == "plain"
        assert got.subject_id == "default"
        assert got.locator == path_to_locator("/abs/a")

    async def test_get_by_locator(self, store: WorkspaceStore) -> None:
        rec = _record(locator=path_to_locator("/abs/loc-a"))
        await store.upsert(rec)
        got = await store.get_by_locator(path_to_locator("/abs/loc-a"))
        assert got is not None
        assert got.workspace_id == "wid-1"

    async def test_get_missing_returns_none(self, store: WorkspaceStore) -> None:
        assert await store.get("nope") is None
        assert await store.get_by_locator(path_to_locator("/abs/nope")) is None

    async def test_upsert_replaces(self, store: WorkspaceStore) -> None:
        rec = _record(name="old")
        await store.upsert(rec)
        rec2 = WorkspaceRecord(
            workspace_id="wid-1",
            name="new",
            provider_type="plain",
            subject_id="default",
            locator=path_to_locator("/abs/agent-x"),
            updated_at=_now(),
        )
        await store.upsert(rec2)
        got = await store.get("wid-1")
        assert got is not None
        assert got.name == "new"

    async def test_list_filters_by_provider_type(self, store: WorkspaceStore) -> None:
        await store.upsert(_record(workspace_id="a1", locator=path_to_locator("/abs/a1")))
        await store.upsert(
            _record(
                workspace_id="b1",
                provider_type="backup",
                locator=path_to_locator("/abs/b1"),
            )
        )
        plains = await store.list(provider_type="plain")
        assert {r.workspace_id for r in plains} == {"a1"}
        others = await store.list(provider_type="backup")
        assert {r.workspace_id for r in others} == {"b1"}
        all_active = await store.list_all_active()
        assert {r.workspace_id for r in all_active} == {"a1", "b1"}

    async def test_list_filters_by_subject_id(self, store: WorkspaceStore) -> None:
        await store.upsert(
            _record(workspace_id="d1", subject_id="default", locator=path_to_locator("/abs/d1"))
        )
        await store.upsert(
            _record(
                workspace_id="o1",
                subject_id="other",
                locator=path_to_locator("/abs/o1"),
            )
        )
        default = await store.list(subject_id="default")
        assert {r.workspace_id for r in default} == {"d1"}


# ─── B. WorkspaceStore 软删 ───


class TestStoreSoftDelete:
    async def test_soft_delete_excludes_by_default(self, store: WorkspaceStore) -> None:
        await store.upsert(_record(locator=path_to_locator("/abs/d")))
        assert await store.soft_delete("wid-1") is True
        assert await store.get("wid-1") is None
        assert await store.get("wid-1", include_deleted=True) is not None
        assert await store.list_all_active() == []

    async def test_soft_delete_repeated_returns_false(self, store: WorkspaceStore) -> None:
        await store.upsert(_record(locator=path_to_locator("/abs/d")))
        assert await store.soft_delete("wid-1") is True
        assert await store.soft_delete("wid-1") is False

    async def test_soft_delete_missing_returns_false(self, store: WorkspaceStore) -> None:
        assert await store.soft_delete("nope") is False


# ─── C. WorkspaceStore 重启重建 ───


class TestStoreRestart:
    async def test_persists_across_restart(self, tmp_path: Path) -> None:
        db = tmp_path / "ws.db"
        store = WorkspaceStore(db)
        await store.start()
        await store.upsert(_record(locator=path_to_locator("/abs/persist")))
        await store.stop()

        store2 = WorkspaceStore(db)
        await store2.start()
        try:
            got = await store2.get("wid-1")
            assert got is not None
            assert got.locator == path_to_locator("/abs/persist")
        finally:
            await store2.stop()

    async def test_ddl_idempotent(self, tmp_path: Path) -> None:
        store = WorkspaceStore(tmp_path / "ws.db")
        await store.start()
        await store.stop()
        # 重复 start 不报错（IF NOT EXISTS）
        await store.start()
        await store.stop()


# ─── D. legacy git 记录自动 retag ───


class TestLegacyGitRetag:
    async def test_git_records_retagged_to_plain_on_start(self, tmp_path: Path) -> None:
        db = tmp_path / "ws.db"
        store = WorkspaceStore(db)
        await store.start()
        await store.upsert(
            _record(
                workspace_id="g1",
                provider_type="git",
                locator=path_to_locator("/abs/g1"),
            )
        )
        # 软删的 git 记录一并迁移（防复活路径命中未知 provider）
        await store.upsert(
            _record(workspace_id="g2", provider_type="git", locator=path_to_locator("/abs/g2"))
        )
        await store.soft_delete("g2")
        await store.stop()

        store2 = WorkspaceStore(db)
        await store2.start()
        try:
            active = await store2.get("g1")
            assert active is not None
            assert active.provider_type == "plain"
            deleted = await store2.get("g2", include_deleted=True)
            assert deleted is not None
            assert deleted.provider_type == "plain"
        finally:
            await store2.stop()

    async def test_retag_idempotent_across_restarts(self, tmp_path: Path) -> None:
        db = tmp_path / "ws.db"
        for _ in range(2):
            store = WorkspaceStore(db)
            await store.start()
            await store.stop()
        store = WorkspaceStore(db)
        await store.start()
        got = await store.get("nope")
        assert got is None
        await store.stop()
