# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Sandbox executor built-in Subject unit."""

from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.service_keys import SANDBOX_EXECUTOR
from ghrah.subject.sandbox.executor import SandboxExecutor, SandboxExecutorConfig
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta

__all__ = ["SandboxUnit"]


class SandboxUnit(SubjectUnit):
    """Owns the shared sandbox executor used by workspace and ability units."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._service: SandboxExecutor | None = None
        self._meta = UnitMeta(
            name="sandbox",
            routes=RouteSpec(),
            provides=frozenset({SANDBOX_EXECUTOR}),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> SandboxExecutor:
        if self._service is None:
            raise RuntimeError("SandboxUnit has not been initialized.")
        return self._service

    async def init(self, ctx: Any) -> None:
        sandbox_config = SandboxExecutorConfig(
            default_timeout=self._config.sandbox.default_timeout,
        )
        self._service = SandboxExecutor(
            workspace_root=self._config.sandbox.workspace_root,
            config=sandbox_config,
        )
        ctx.provide(SANDBOX_EXECUTOR.name, self._service)

    async def start(self) -> None:
        await self.service.start()

    async def stop(self) -> None:
        if self._service is not None:
            await self._service.stop()
