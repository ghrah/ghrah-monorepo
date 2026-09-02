# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WorkspaceStore + 结构化 marker 单测。

覆盖：
- 持久化往返（upsert/get/get_by_locator/list，含重启重建）；
- 软删（soft_delete 排除、重复返回 False、include_deleted 取回）；
- marker JSON 读写 + 三要素校验（adopt_marker_matches）；
- 旧格式 marker 不自动认领；
- provider.adopt provider_type 误认领防护（git 拒认领 plain marker 目录）。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.workspace import (
    GitWorkspaceProvider,
    PlainWorkspaceProvider,
    WorkspaceRecord,
    WorkspaceStore,
    path_to_locator,
)
from ghrah.subject.workspace.marker import (
    MARKER_FILENAME,
    adopt_marker_matches,
    read_marker,
    write_marker,
)

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
    provider_type: str = "git",
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
        assert got.provider_type == "git"
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
            provider_type="git",
            subject_id="default",
            locator=path_to_locator("/abs/agent-x"),
            updated_at=_now(),
        )
        await store.upsert(rec2)
        got = await store.get("wid-1")
        assert got is not None
        assert got.name == "new"

    async def test_list_filters_by_provider_type(self, store: WorkspaceStore) -> None:
        await store.upsert(_record(workspace_id="g1", locator=path_to_locator("/abs/g1")))
        await store.upsert(
            _record(
                workspace_id="p1",
                provider_type="plain",
                locator=path_to_locator("/abs/p1"),
            )
        )
        gits = await store.list(provider_type="git")
        assert {r.workspace_id for r in gits} == {"g1"}
        plains = await store.list(provider_type="plain")
        assert {r.workspace_id for r in plains} == {"p1"}
        all_active = await store.list_all_active()
        assert {r.workspace_id for r in all_active} == {"g1", "p1"}

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


# ─── D. 结构化 marker 读写 + 三要素校验 ───


class TestMarker:
    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        rec = _record(locator=path_to_locator(str(tmp_path / "ws")))
        d = str(tmp_path / "ws")
        os.makedirs(d)
        write_marker(d, rec)
        marker = read_marker(d)
        assert marker is not None
        assert marker.workspace_id == rec.workspace_id
        assert marker.provider_type == "git"
        assert marker.subject_id == "default"
        assert marker.name == "agent-x"

    def test_read_missing_returns_none(self, tmp_path: Path) -> None:
        assert read_marker(str(tmp_path / "nope")) is None

    def test_legacy_marker_returns_none(self, tmp_path: Path) -> None:
        d = str(tmp_path / "legacy")
        os.makedirs(d)
        with open(os.path.join(d, MARKER_FILENAME), "w") as f:
            f.write("# Workspace for agent: legacy\n")
        assert read_marker(d) is None

    def test_corrupt_json_returns_none(self, tmp_path: Path) -> None:
        d = str(tmp_path / "corrupt")
        os.makedirs(d)
        with open(os.path.join(d, MARKER_FILENAME), "w") as f:
            f.write("{not json")
        assert read_marker(d) is None

    def test_missing_fields_returns_none(self, tmp_path: Path) -> None:
        d = str(tmp_path / "partial")
        os.makedirs(d)
        with open(os.path.join(d, MARKER_FILENAME), "w") as f:
            f.write('{"workspace_id": "x"}\n')
        assert read_marker(d) is None


class TestAdoptMarkerMatches:
    def test_full_match(self) -> None:
        from ghrah.subject.workspace.marker import MarkerData

        marker = MarkerData(
            workspace_id="wid",
            provider_type="git",
            subject_id="default",
            created_at=None,
            name="x",
        )
        assert adopt_marker_matches(
            marker, workspace_id="wid", provider_type="git", subject_id="default"
        )

    def test_workspace_id_mismatch_rejects(self) -> None:
        from ghrah.subject.workspace.marker import MarkerData

        marker = MarkerData(
            workspace_id="wid",
            provider_type="git",
            subject_id="default",
            created_at=None,
            name=None,
        )
        assert not adopt_marker_matches(marker, workspace_id="other")

    def test_provider_type_mismatch_rejects(self) -> None:
        from ghrah.subject.workspace.marker import MarkerData

        marker = MarkerData(
            workspace_id="wid",
            provider_type="plain",
            subject_id="default",
            created_at=None,
            name=None,
        )
        assert not adopt_marker_matches(marker, provider_type="git")

    def test_subject_id_mismatch_rejects(self) -> None:
        from ghrah.subject.workspace.marker import MarkerData

        marker = MarkerData(
            workspace_id="wid",
            provider_type="git",
            subject_id="other",
            created_at=None,
            name=None,
        )
        assert not adopt_marker_matches(marker, subject_id="default")

    def test_none_marker_rejects(self) -> None:
        assert not adopt_marker_matches(None, provider_type="git")

    def test_partial_check_only_given(self) -> None:
        from ghrah.subject.workspace.marker import MarkerData

        marker = MarkerData(
            workspace_id="wid",
            provider_type="git",
            subject_id="other",
            created_at=None,
            name=None,
        )
        # 只校验 provider_type，subject_id 差异忽略
        assert adopt_marker_matches(marker, provider_type="git")


# ─── E. provider.adopt 误认领防护 ───


class TestAdoptProviderTypeMismatch:
    async def test_git_rejects_plain_marker_dir(self, tmp_path: Path) -> None:
        root = str(tmp_path / "root")
        os.makedirs(root)
        sandbox = SandboxExecutor(workspace_root=root)
        await sandbox.start()
        try:
            git_provider = GitWorkspaceProvider(sandbox)
            plain_provider = PlainWorkspaceProvider()
            d = str(tmp_path / "root" / "plaindir")
            os.makedirs(d)
            plain_rec = _record(
                workspace_id="p1",
                provider_type="plain",
                locator=path_to_locator(d),
            )
            await plain_provider.init(plain_rec)
            # git provider 不应认领带 plain marker 的目录
            assert await git_provider.adopt(path_to_locator(d)) is None
            # plain provider 应认领
            result = await plain_provider.adopt(path_to_locator(d))
            assert result is not None
            assert result.provider_type == "plain"
        finally:
            await sandbox.stop()

    async def test_plain_rejects_git_marker_dir(self, tmp_path: Path) -> None:
        root = str(tmp_path / "root")
        os.makedirs(root)
        sandbox = SandboxExecutor(workspace_root=root)
        await sandbox.start()
        try:
            git_provider = GitWorkspaceProvider(sandbox)
            plain_provider = PlainWorkspaceProvider()
            d = str(tmp_path / "root" / "gitdir")
            git_rec = _record(workspace_id="g1", provider_type="git", locator=path_to_locator(d))
            await git_provider.init(git_rec)
            assert await plain_provider.adopt(path_to_locator(d)) is None
            result = await git_provider.adopt(path_to_locator(d))
            assert result is not None
            assert result.provider_type == "git"
        finally:
            await sandbox.stop()
