from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ghrah.protocol.types import ProjectStatus, RecoveryAction

from ghrah.subject.project.models import (
    AgentSpec,
    ProjectRecord,
    RecoverySpec,
    WorkspaceMount,
    make_project_record,
)
from ghrah.subject.project.store import (
    ConcurrentModificationError,
    ProjectNotFoundError,
    ProjectStore,
)

# ─── fixtures / helpers ───


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[ProjectStore]:
    s = ProjectStore(tmp_path / "projects.db")
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


def _make(
    *,
    project_id: str = "a" * 32,
    name: str = "P1",
    status: ProjectStatus = ProjectStatus.ACTIVE,
    workspaces: list[WorkspaceMount] | None = None,
    agents: list[AgentSpec] | None = None,
    version: int = 1,
    deleted: bool = False,
) -> ProjectRecord:
    now = datetime.now(UTC)
    return ProjectRecord(
        project_id=project_id,
        name=name,
        status=status,
        workspaces=list(workspaces) if workspaces else [],
        agents=list(agents) if agents else [],
        created_at=now,
        updated_at=now,
        version=version,
        deleted_at=now if deleted else None,
    )


# ─── A. 基本 CRUD + JSON 往返 ───


class TestCrudAndRoundtrip:
    async def test_start_idempotent(self, tmp_path: Path) -> None:
        s = ProjectStore(tmp_path / "p.db")
        await s.start()
        await s.start()  # 不报错
        await s.stop()

    async def test_upsert_and_get(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        got = await store.get(record.project_id)
        assert got is not None
        assert got.name == "P1"
        assert got.project_id == record.project_id

    async def test_get_missing_returns_none(self, store: ProjectStore) -> None:
        assert await store.get("nonexistent") is None

    async def test_json_columns_roundtrip(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        record.cluster_ids = ["c1", "c2"]
        record.workspaces = [
            WorkspaceMount(workspace_id="ws-1", default_for_agents=True),
            WorkspaceMount(workspace_id="ws-2", role="scratch"),
        ]
        record.agents = [AgentSpec(name="a1", cluster_id="c1", path_grants=[])]
        record.task_ids = ["t1", "t2"]
        await store.upsert(record)
        got = await store.get(record.project_id)
        assert got is not None
        assert got.cluster_ids == ["c1", "c2"]
        assert len(got.workspaces) == 2
        assert got.workspaces[0].default_for_agents is True
        assert got.workspaces[1].role == "scratch"
        assert got.agents[0].name == "a1"
        assert got.task_ids == ["t1", "t2"]

    async def test_recovery_roundtrip(self, store: ProjectStore) -> None:
        record = make_project_record(
            name="P1", recovery=RecoverySpec(on_restart=RecoveryAction.PAUSE)
        )
        await store.upsert(record)
        got = await store.get(record.project_id)
        assert got is not None
        assert got.recovery.on_restart is RecoveryAction.PAUSE

    async def test_status_roundtrip(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        record.status = ProjectStatus.PAUSED
        await store.upsert(record)
        got = await store.get(record.project_id)
        assert got is not None
        assert got.status is ProjectStatus.PAUSED

    async def test_dt_roundtrip(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        ts = datetime(2026, 7, 31, 10, 0, 0, tzinfo=UTC)
        record.created_at = ts
        record.updated_at = ts
        await store.upsert(record)
        got = await store.get(record.project_id)
        assert got is not None
        assert got.created_at == ts


# ─── B. 乐观锁 update ───


class TestOptimisticLock:
    async def test_update_success(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        updated = await store.update(
            record.project_id, 1, lambda r: r.model_copy(update={"name": "P2"})
        )
        assert updated.name == "P2"
        assert updated.version == 2
        assert updated.updated_at >= record.updated_at

    async def test_update_version_mismatch(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        with pytest.raises(ConcurrentModificationError):
            await store.update(record.project_id, 999, lambda r: r)

    async def test_update_missing_raises_not_found(self, store: ProjectStore) -> None:
        with pytest.raises(ProjectNotFoundError):
            await store.update("nonexistent", 1, lambda r: r)

    async def test_update_chained_versions(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        await store.update(
            record.project_id, 1, lambda r: r.model_copy(update={"name": "P2"})
        )
        v3 = await store.update(
            record.project_id, 2, lambda r: r.model_copy(update={"name": "P3"})
        )
        assert v3.version == 3
        got = await store.get(record.project_id)
        assert got is not None
        assert got.version == 3
        assert got.name == "P3"


# ─── C. 软删 ───


class TestSoftDelete:
    async def test_soft_delete(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        await store.soft_delete(record.project_id, 1)
        assert await store.get(record.project_id) is None
        got = await store.get(record.project_id, include_deleted=True)
        assert got is not None
        assert got.deleted_at is not None
        assert got.version == 2

    async def test_soft_delete_version_mismatch(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        with pytest.raises(ConcurrentModificationError):
            await store.soft_delete(record.project_id, 999)


# ─── D. list / exists ───


class TestListExists:
    async def test_list_empty(self, store: ProjectStore) -> None:
        assert await store.list() == []

    async def test_list_status_filter(self, store: ProjectStore) -> None:
        r1 = make_project_record(name="P1")
        r2 = make_project_record(name="P2")
        r2.status = ProjectStatus.PAUSED
        await store.upsert(r1)
        await store.upsert(r2)
        active = await store.list(status=ProjectStatus.ACTIVE)
        assert [p.name for p in active] == ["P1"]
        paused = await store.list(status=ProjectStatus.PAUSED)
        assert [p.name for p in paused] == ["P2"]

    async def test_list_excludes_deleted(self, store: ProjectStore) -> None:
        r1 = make_project_record(name="P1")
        r2 = make_project_record(name="P2")
        await store.upsert(r1)
        await store.upsert(r2)
        await store.soft_delete(r1.project_id, 1)
        result = await store.list()
        assert [p.name for p in result] == ["P2"]
        result_all = await store.list(include_deleted=True)
        assert {p.name for p in result_all} == {"P1", "P2"}

    async def test_exists(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        assert await store.exists(record.project_id) is True
        assert await store.exists("nonexistent") is False

    async def test_exists_excludes_deleted(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        await store.upsert(record)
        await store.soft_delete(record.project_id, 1)
        assert await store.exists(record.project_id) is False


# ─── E. exists_workspace_mounted ───


class TestExistsWorkspaceMounted:
    async def test_mounted(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        record.workspaces = [WorkspaceMount(workspace_id="ws-1", default_for_agents=True)]
        await store.upsert(record)
        assert await store.exists_workspace_mounted("ws-1") is True

    async def test_not_mounted(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        record.workspaces = [WorkspaceMount(workspace_id="ws-1")]
        await store.upsert(record)
        assert await store.exists_workspace_mounted("ws-99") is False

    async def test_excludes_deleted_project(self, store: ProjectStore) -> None:
        record = make_project_record(name="P1")
        record.workspaces = [WorkspaceMount(workspace_id="ws-1")]
        await store.upsert(record)
        await store.soft_delete(record.project_id, 1)
        assert await store.exists_workspace_mounted("ws-1") is False

    async def test_multiple_projects(self, store: ProjectStore) -> None:
        r1 = make_project_record(name="P1")
        r1.workspaces = [WorkspaceMount(workspace_id="ws-1")]
        r2 = make_project_record(name="P2")
        r2.workspaces = [WorkspaceMount(workspace_id="ws-2")]
        await store.upsert(r1)
        await store.upsert(r2)
        assert await store.exists_workspace_mounted("ws-1") is True
        assert await store.exists_workspace_mounted("ws-2") is True
