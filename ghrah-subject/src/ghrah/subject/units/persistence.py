# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Persistence built-in Subject unit."""

from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.persistence.service import SubjectPersistenceService
from ghrah.subject.runtime.service_keys import PERSISTENCE
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import PERSIST_COMMANDS

__all__ = ["PersistenceUnit"]


class PersistenceUnit(SubjectUnit):
    """Owns the Subject persistence service and persist_* command routes."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._service: SubjectPersistenceService | None = None
        self._meta = UnitMeta(
            name="persistence",
            routes=RouteSpec(commands=PERSIST_COMMANDS),
            provides=frozenset({PERSISTENCE}),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> SubjectPersistenceService:
        if self._service is None:
            raise RuntimeError("PersistenceUnit has not been initialized.")
        return self._service

    async def init(self, ctx: Any) -> None:
        self._service = SubjectPersistenceService(db_path=self._config.persistence.db_path)
        ctx.provide(PERSISTENCE.name, self._service)

    async def start(self) -> None:
        await self.service.start()

    async def stop(self) -> None:
        if self._service is not None:
            await self._service.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        return await self.service.handle_command(command, payload)
