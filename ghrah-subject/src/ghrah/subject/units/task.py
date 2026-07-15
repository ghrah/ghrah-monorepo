# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Task management built-in Subject unit."""

from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SUBJECT_CORE_EVENT_RECEIVED
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import TASK_MANAGER
from ghrah.subject.task import TaskManager, TaskStore
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
        self._ctx: SubjectContext | None = None
        self._store: TaskStore | None = None
        self._manager: TaskManager | None = None
        self._meta = UnitMeta(
            name="task",
            provides=frozenset({TASK_MANAGER}),
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

    async def init(self, ctx: SubjectContext) -> None:
        self._ctx = ctx
        self._store = TaskStore(ctx.config.persistence.db_path)
        self._manager = TaskManager(self._store, on_event=self._emit_event)
        ctx.services.set(TASK_MANAGER, self._manager)

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

    async def _emit_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        await ctx.event_bus.emit(
            SUBJECT_CORE_EVENT_RECEIVED,
            {"event_type": event_type, "payload": payload},
        )
