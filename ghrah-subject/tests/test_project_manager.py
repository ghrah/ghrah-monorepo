from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from ghrah.protocol.types import RecoveryAction

from ghrah.subject.project.manager import ProjectManager
from ghrah.subject.project.models import (
    ProjectStatus,
)
from ghrah.subject.project.store import ProjectStore
from ghrah.subject.workspace.models import WorkspaceRecord
from ghrah.subject.workspace.providers.git import path_to_locator

# ─── fakes ───


@dataclass
class _FakeAgentWorkspace:
    record: WorkspaceRecord
    path: str = "ws"


class _FakeWorkspaceManager:
    """Fake WorkspaceManager：register/list/get_record，不触文件系统。"""

    def __init__(self) -> None:
        self._records: dict[str, WorkspaceRecord] = {}

    def list_records(self) -> list[WorkspaceRecord]:
        return list(self._records.values())

    def get_record(self, workspace_id: str) -> WorkspaceRecord | None:
        return self._records.get(workspace_id)

    async def register_workspace(
        self, locator: str, *, name: str = "", provider_type: str | None = None
    ) -> _FakeAgentWorkspace:
        record = WorkspaceRecord(
            name=name or "default",
            provider_type=provider_type or "git",
            subject_id="default",
            locator=locator,
        )
        self._records[record.workspace_id] = record
        return _FakeAgentWorkspace(record=record)


class _FakeTaskMgr:
    def __init__(self, task_exists: bool = True) -> None:
        self._exists = task_exists

    async def handle_command(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command == "task_get":
            if self._exists:
                return {"success": True, "data": {"task_id": payload.get("task_id")}}
            return {"success": False, "data": None, "error": "not found"}
        return {"success": False, "data": None, "error": "unsupported"}


class _FakeClusterTransport:
    def __init__(self) -> None:
        self.ensured: list[str] = []
        self.shutdowns: list[str] = []
        self._handle = _FakeHandle()

    async def ensure_cluster(self, cluster_id: str) -> _FakeHandle:
        self.ensured.append(cluster_id)
        return self._handle

    def get_handle(self, cluster_id: str) -> _FakeHandle:
        return self._handle

    def has_cluster(self, cluster_id: str) -> bool:
        return True

    async def shutdown_cluster(self, cluster_id: str) -> None:
        self.shutdowns.append(cluster_id)

    async def stop(self) -> None:
        pass


class _FakeHandle:
    def __init__(self) -> None:
        self.spawned: list[str] = []
        self.terminated: list[str] = []
        self._list: list[dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        return True

    async def spawn_agent(self, payload: Any) -> dict[str, Any]:
        self.spawned.append(payload.config.name)
        return {"success": True, "data": {"name": payload.config.name}, "error": None}

    async def list_agents(self) -> list[dict[str, Any]]:
        return list(self._list)

    async def terminate_agent(self, agent_name: str) -> dict[str, Any]:
        self.terminated.append(agent_name)
        return {"success": True, "data": None, "error": None}

    async def shutdown(self) -> None:
        pass


class _FakeManifestStore:
    pass


def _default_locator(tmp_path: Path) -> str:
    return path_to_locator(str(tmp_path / "default"))


# ─── fixtures ───


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[ProjectStore]:
    s = ProjectStore(tmp_path / "projects.db")
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


def _make_manager(
    store: ProjectStore,
    *,
    events: list[tuple[str, dict[str, Any]]] | None = None,
    default_locator: str = "file:///workspaces/default",
    task_mgr: _FakeTaskMgr | None = None,
) -> ProjectManager:
    async def on_event(event_type: str, payload: dict[str, Any]) -> None:
        if events is not None:
            events.append((event_type, payload))

    return ProjectManager(
        store,
        _FakeWorkspaceManager(),
        task_mgr or _FakeTaskMgr(),
        _FakeClusterTransport(),
        _FakeManifestStore(),
        on_event=on_event if events is not None else None,
        default_workspace_locator=default_locator,
        default_db_path_template="~/.ghrah/projects/{project_id}.db",
    )


class TestProjectCreate:
    async def test_create_success(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        events: list[tuple[str, dict[str, Any]]] = []
        mgr = _make_manager(store, events=events, default_locator=_default_locator(tmp_path))
        result = await mgr.handle_command(
            "project_create",
            {"name": "P1", "default_workspace_locator": _default_locator(tmp_path)},
        )
        assert result["success"], result.get("error")
        project = result["data"]["project"]
        assert project["name"] == "P1"
        assert len(project["cluster_ids"]) == 1
        assert len(project["workspaces"]) == 1
        assert project["workspaces"][0]["default_for_agents"] is True
        assert project["status"] == ProjectStatus.ACTIVE.value
        # 事件
        assert events[0][0] == "project_created"

    async def test_create_requires_name(self, store: ProjectStore) -> None:
        mgr = _make_manager(store)
        result = await mgr.handle_command("project_create", {})
        assert not result["success"]
        assert "name" in (result["error"] or "")

    async def test_create_requires_locator(self, store: ProjectStore) -> None:
        mgr = _make_manager(store, default_locator="")
        result = await mgr.handle_command("project_create", {"name": "P1"})
        assert not result["success"]
        assert "locator" in (result["error"] or "")


class TestProjectGetList:
    async def test_get_and_list(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        created = await mgr.handle_command(
            "project_create",
            {"name": "P1", "default_workspace_locator": _default_locator(tmp_path)},
        )
        project_id = created["data"]["project"]["project_id"]

        got = await mgr.handle_command("project_get", {"project_id": project_id})
        assert got["success"]
        assert got["data"]["project"]["project_id"] == project_id

        listed = await mgr.handle_command("project_list", {})
        assert listed["success"]
        assert listed["data"]["count"] == 1

    async def test_get_missing(self, store: ProjectStore) -> None:
        mgr = _make_manager(store)
        result = await mgr.handle_command("project_get", {"project_id": "nope"})
        assert not result["success"]


class TestProjectAddRemoveAgent:
    async def _create(self, mgr: ProjectManager, tmp_path: Path) -> dict[str, Any]:
        return await mgr.handle_command(
            "project_create",
            {"name": "P1", "default_workspace_locator": _default_locator(tmp_path)},
        )

    async def test_add_agent(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        events: list[tuple[str, dict[str, Any]]] = []
        mgr = _make_manager(store, events=events, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        project = created["data"]["project"]
        cluster_id = project["cluster_ids"][0]
        workspace_id = project["workspaces"][0]["workspace_id"]

        result = await mgr.handle_command(
            "project_add_agent",
            {
                "project_id": project["project_id"],
                "agent": {
                    "name": "a1",
                    "cluster_id": cluster_id,
                    "path_grants": [
                        {"workspace_id": workspace_id, "subpath": "."}
                    ],
                },
            },
        )
        assert result["success"], result.get("error")
        assert len(result["data"]["project"]["agents"]) == 1
        assert events[-1][0] == "project_agent_added"
        # spawn 调用
        assert mgr._cluster_transport._handle.spawned == ["a1"]  # type: ignore[attr-defined]

    async def test_add_agent_rejects_unknown_cluster(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        result = await mgr.handle_command(
            "project_add_agent",
            {
                "project_id": created["data"]["project"]["project_id"],
                "agent": {"name": "a1", "cluster_id": "unknown-cluster"},
            },
        )
        assert not result["success"]
        assert "cluster_id" in (result["error"] or "")

    async def test_remove_agent(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        events: list[tuple[str, dict[str, Any]]] = []
        mgr = _make_manager(store, events=events, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        project = created["data"]["project"]
        cluster_id = project["cluster_ids"][0]
        await mgr.handle_command(
            "project_add_agent",
            {
                "project_id": project["project_id"],
                "agent": {"name": "a1", "cluster_id": cluster_id},
            },
        )
        result = await mgr.handle_command(
            "project_remove_agent",
            {"project_id": project["project_id"], "agent_name": "a1"},
        )
        assert result["success"], result.get("error")
        assert result["data"]["project"]["agents"] == []
        assert events[-1][0] == "project_agent_removed"


class TestProjectStatusTransitions:
    async def _create(self, mgr: ProjectManager, tmp_path: Path) -> dict[str, Any]:
        return await mgr.handle_command(
            "project_create",
            {"name": "P1", "default_workspace_locator": _default_locator(tmp_path)},
        )

    async def test_pause_resume_stop(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        events: list[tuple[str, dict[str, Any]]] = []
        mgr = _make_manager(store, events=events, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        pid = created["data"]["project"]["project_id"]
        ct = mgr._cluster_transport  # type: ignore[attr-defined]

        paused = await mgr.handle_command("project_pause", {"project_id": pid})
        assert paused["success"]
        assert paused["data"]["project"]["status"] == ProjectStatus.PAUSED.value
        assert ct.shutdowns  # pause shutdown cluster

        resumed = await mgr.handle_command("project_resume", {"project_id": pid})
        assert resumed["success"]
        assert resumed["data"]["project"]["status"] == ProjectStatus.ACTIVE.value

        stopped = await mgr.handle_command("project_stop", {"project_id": pid})
        assert stopped["success"]
        assert stopped["data"]["project"]["status"] == ProjectStatus.STOPPED.value

    async def test_illegal_transition_rejected(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        pid = created["data"]["project"]["project_id"]
        # ACTIVE -> STOPPED 直接（合法），但 PAUSED -> ACTIVE 后再 PAUSED...
        stopped = await mgr.handle_command("project_stop", {"project_id": pid})
        assert stopped["success"]
        # STOPPED -> PAUSED 非法
        bad = await mgr.handle_command("project_pause", {"project_id": pid})
        assert not bad["success"]
        assert "transition" in (bad["error"] or "")


class TestProjectSetRecoveryAndDelete:
    async def _create(self, mgr: ProjectManager, tmp_path: Path) -> dict[str, Any]:
        return await mgr.handle_command(
            "project_create",
            {"name": "P1", "default_workspace_locator": _default_locator(tmp_path)},
        )

    async def test_set_recovery(self, store: ProjectStore, tmp_path: Path) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        pid = created["data"]["project"]["project_id"]
        result = await mgr.handle_command(
            "project_set_recovery",
            {"project_id": pid, "recovery": RecoveryAction.PAUSE},
        )
        assert result["success"]
        assert result["data"]["project"]["recovery"] == RecoveryAction.PAUSE.value

    async def test_delete(self, store: ProjectStore, tmp_path: Path) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        pid = created["data"]["project"]["project_id"]
        result = await mgr.handle_command("project_delete", {"project_id": pid})
        assert result["success"]
        assert result["data"]["deleted"] is True
        # 软删后 get 返回 None
        assert await store.get(pid) is None

    async def test_delete_missing(self, store: ProjectStore) -> None:
        mgr = _make_manager(store)
        result = await mgr.handle_command("project_delete", {"project_id": "nope"})
        assert not result["success"]


class TestProjectLinkTask:
    async def _create(self, mgr: ProjectManager, tmp_path: Path) -> dict[str, Any]:
        return await mgr.handle_command(
            "project_create",
            {"name": "P1", "default_workspace_locator": _default_locator(tmp_path)},
        )

    async def test_link_unlink_task(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        created = await self._create(mgr, tmp_path)
        pid = created["data"]["project"]["project_id"]
        linked = await mgr.handle_command(
            "project_link_task", {"project_id": pid, "task_id": "t1"}
        )
        assert linked["success"]
        assert "t1" in linked["data"]["project"]["task_ids"]

        unlinked = await mgr.handle_command(
            "project_unlink_task", {"project_id": pid, "task_id": "t1"}
        )
        assert unlinked["success"]
        assert "t1" not in unlinked["data"]["project"]["task_ids"]

    async def test_link_task_missing_task_rejected(
        self, store: ProjectStore, tmp_path: Path
    ) -> None:
        mgr = _make_manager(
            store,
            default_locator=_default_locator(tmp_path),
            task_mgr=_FakeTaskMgr(task_exists=False),
        )
        created = await self._create(mgr, tmp_path)
        pid = created["data"]["project"]["project_id"]
        result = await mgr.handle_command(
            "project_link_task", {"project_id": pid, "task_id": "t1"}
        )
        assert not result["success"]
        assert "task not found" in (result["error"] or "")


class TestBootstrapMethods:
    async def test_bootstrap_default_project(self, store: ProjectStore, tmp_path: Path) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        project = await mgr.bootstrap_default_project()
        assert project.name == "default"
        assert project.cluster_ids == ["default"]
        assert len(project.workspaces) == 1
        assert project.workspaces[0].default_for_agents is True
        # 持久化
        loaded = await store.get(project.project_id)
        assert loaded is not None
        assert loaded.name == "default"

    async def test_adopt_existing_agents(self, store: ProjectStore, tmp_path: Path) -> None:
        mgr = _make_manager(store, default_locator=_default_locator(tmp_path))
        project = await mgr.bootstrap_default_project()
        # 让 fake handle 返回现有 agent
        mgr._cluster_transport._handle._list = [  # type: ignore[attr-defined]
            {"name": "existing-agent"}
        ]
        specs = await mgr.adopt_existing_agents(project.project_id, "default")
        assert len(specs) == 1
        assert specs[0].name == "existing-agent"
        loaded = await store.get(project.project_id)
        assert loaded is not None
        assert any(a.name == "existing-agent" for a in loaded.agents)

    async def test_bootstrap_requires_locator(self, store: ProjectStore) -> None:
        mgr = _make_manager(store, default_locator="")
        with pytest.raises(ValueError, match="locator"):
            await mgr.bootstrap_default_project()

    async def test_handle_unknown_command(self, store: ProjectStore) -> None:
        mgr = _make_manager(store)
        result = await mgr.handle_command("project_mystery", {})
        assert not result["success"]
