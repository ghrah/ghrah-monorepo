# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Task management built-in Subject unit."""

from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.project.errors import ProjectArchivedError
from ghrah.subject.project.scoped_stores import ProjectScopedTaskStore
from ghrah.subject.runtime.service_keys import PROJECT_MANAGER, TASK_MANAGER, TASK_STORE
from ghrah.subject.task import TaskManager
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import TASK_COMMANDS

__all__ = ["TaskUnit"]


class TaskUnit(SubjectUnit):
    """Owns TaskStore + TaskManager and task command/event routes.

    A thin wrapper around :class:`TaskManager`: it wires the manager's
    ``on_event`` callback to the internal event bus so task events reach the
    observer endpoint, and registers the manager under the ``TASK_MANAGER``
    service key for other units (e.g. Stage 4 DelegationAbility).
    """

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ctx: Any | None = None
        self._store: ProjectScopedTaskStore | None = None
        self._manager: TaskManager | None = None
        self._meta = UnitMeta(
            name="task",
            provides=frozenset({TASK_MANAGER, TASK_STORE}),
            routes=RouteSpec(commands=TASK_COMMANDS),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> TaskManager:
        if self._manager is None:
            raise RuntimeError("TaskUnit has not been initialized.")
        return self._manager

    async def init(self, ctx: Any) -> None:
        self._ctx = ctx
        async def project_roots() -> dict[str, str]:
            try:
                manager = ctx.get(PROJECT_MANAGER.name)
            except Exception:  # noqa: BLE001 — ProjectUnit 在本 Unit 之后挂载
                return {}
            if manager is None:
                return {}
            result = await manager.handle_command(
                "project_list", {"archived": None}
            )
            projects = (result.get("data") or {}).get("projects", [])
            return {
                p["project_id"]: p["project_root_locator"]
                for p in projects
                if p.get("project_root_locator")
            }

        self._store = ProjectScopedTaskStore(
            self._config.persistence.db_path, project_roots
        )
        self._manager = TaskManager(self._store, on_event=self._emit_event)
        ctx.provide(TASK_MANAGER.name, self._manager)
        ctx.provide(TASK_STORE.name, self._store)

    async def start(self) -> None:
        if self._store is not None:
            await self._store.start()

    async def stop(self) -> None:
        if self._store is not None:
            await self._store.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        try:
            error = await self._guard_project_access(payload)
            if error is not None:
                return error
            normalized = await self._normalize_agent_identity(command, payload)
            if normalized.get("success") is False:
                return normalized
            return await self.service.handle_command(command, normalized)
        except ProjectArchivedError:
            return {"success": False, "data": None, "error": "resource_archived"}

    async def _guard_project_access(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Reject Task commands before a frozen Project Root is read or written."""

        ctx = self._ctx
        store = self._store
        if ctx is None or store is None:
            return None
        try:
            manager = ctx.get(PROJECT_MANAGER.name)
        except Exception:  # noqa: BLE001 — coexistence profile has no ProjectUnit
            return None
        if manager is None:
            return None
        project_id = str(payload.get("project_id") or "")
        if not project_id and payload.get("task_id"):
            task = await store.get(str(payload["task_id"]), include_deleted=True)
            project_id = task.project_id if task is not None else ""
        if not project_id:
            return None
        result = await manager.handle_command(
            "project_get", {"project_id": project_id}
        )
        if not result.get("success"):
            return {
                "success": False,
                "data": None,
                "error": result.get("error") or f"project not found: {project_id}",
            }
        project = (result.get("data") or {}).get("project") or {}
        if project.get("archived_at") or project.get("deleted_at"):
            return {"success": False, "data": None, "error": "resource_archived"}
        return None

    async def _normalize_agent_identity(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """在 Task 写边界将 project 内 Agent 名解析为稳定 agent_id。"""
        if command not in {"task_create", "task_update", "task_assign"}:
            return payload
        value_id = str(payload.get("agent_id") or "")
        value_name = str(payload.get("agent_name") or "")
        if not value_id and not value_name:
            return payload
        ctx = self._ctx
        store = self._store
        if ctx is None or store is None:
            return payload
        try:
            project_manager = ctx.get(PROJECT_MANAGER.name)
        except Exception:  # noqa: BLE001 — coexistence profile 无 ProjectUnit
            return payload
        if project_manager is None:
            return payload
        project_id = str(payload.get("project_id") or "")
        if not project_id and payload.get("task_id"):
            task = await store.get(str(payload["task_id"]))
            project_id = task.project_id if task is not None else ""
        if not project_id:
            return payload
        result = await project_manager.handle_command(
            "project_get", {"project_id": project_id}
        )
        project = (result.get("data") or {}).get("project") or {}
        agents = project.get("agents") or []
        matches = [
            agent
            for agent in agents
            if (value_id and agent.get("agent_id") == value_id)
            or (not value_id and value_name and agent.get("name") == value_name)
        ]
        if len(matches) > 1:
            return {
                "success": False,
                "data": None,
                "error": f"ambiguous agent in task project: {value_name or value_id}",
            }
        if len(matches) == 1:
            normalized = dict(payload)
            normalized["agent_id"] = matches[0].get("agent_id") or ""
            normalized["agent_name"] = matches[0].get("name") or value_name
            return normalized
        return {
            "success": False,
            "data": None,
            "error": "agent_project_mismatch",
        }

    async def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """TaskManager 的 ``on_event`` 回调：保留 async 签名，体内同步 ctx.emit。"""

        ctx = self._ctx
        if ctx is None:
            return
        ctx.emit(f"event/{event_type}", payload)
