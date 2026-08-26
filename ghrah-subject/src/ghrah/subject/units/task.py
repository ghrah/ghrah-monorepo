# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Task management built-in Subject unit."""

from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
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
            result = await manager.handle_command("project_list", {})
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
        return await self.service.handle_command(command, payload)

    async def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """TaskManager 的 ``on_event`` 回调：保留 async 签名，体内同步 ctx.emit。"""

        ctx = self._ctx
        if ctx is None:
            return
        ctx.emit(f"event/{event_type}", payload)
