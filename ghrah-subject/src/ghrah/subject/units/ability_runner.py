# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ability runner built-in Subject unit (序 9).

Owns the AbilityRunner and routes the long-running ``execute_ability`` command.
Implements D4 phase 1: injects ``workspace`` (typed WorkspaceService) and
``event_bus`` (internal SubjectEventBus) via constructor so the unit path no
longer depends on the legacy ``bind_*`` callbacks. ``sandbox_executor`` is also
injected so ``execute_command`` abilities run under the Subject sandbox.
"""

from __future__ import annotations

import logging
from typing import Any

from ghrah.abilities import ActionOutcome
from ghrah.subject.ability_runner import AbilityRunner, AbilityRunnerConfig
from ghrah.subject.config import SubjectConfig
from ghrah.subject.permission_checker import PermissionChecker
from ghrah.subject.runtime.service_keys import (
    ABILITY_EXECUTOR,
    HITL_NOTARY,
    PERMISSION_SERVICE,
    SANDBOX_EXECUTOR,
    WORKSPACE_SERVICE,
)
from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta

__all__ = ["AbilityRunnerUnit"]

logger = logging.getLogger(__name__)


class _CtxEventBusAdapter:
    """``SubjectEventBus``-shaped adapter backed by Ouroboros ``ctx.emit``.

    ``emit`` 保留 async 签名（AbilityRunner ``await self._event_bus.emit``），
    体内同步转发到 ``ctx.emit(f"event/{type}", payload)``。
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    async def emit(self, event_type: str, payload: Any) -> None:
        self._ctx.emit(f"event/{event_type}", payload)


class AbilityRunnerUnit(SubjectUnit):
    """Owns AbilityRunner and the ``execute_ability`` long-running route."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._runner: AbilityRunner | None = None
        self._meta = UnitMeta(
            name="ability_runner",
            requires=frozenset({
                HITL_NOTARY,
                PERMISSION_SERVICE,
                WORKSPACE_SERVICE,
                SANDBOX_EXECUTOR,
            }),
            provides=frozenset({ABILITY_EXECUTOR}),
            # D10：只声明 long_running_commands，不重复放入 commands。
            routes=RouteSpec(long_running_commands=frozenset({"execute_ability"})),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> AbilityRunner:
        if self._runner is None:
            raise RuntimeError("AbilityRunnerUnit has not been initialized.")
        return self._runner

    async def init(self, ctx: Any) -> None:
        notary = ctx.get(HITL_NOTARY.name)
        permission_service = ctx.get(PERMISSION_SERVICE.name)
        workspace = ctx.get(WORKSPACE_SERVICE.name)
        sandbox = ctx.get(SANDBOX_EXECUTOR.name)

        if not isinstance(sandbox, SandboxExecutor):
            raise TypeError("SANDBOX_EXECUTOR service must be SandboxExecutor.")
        # PermissionsUnit always stores a concrete PermissionChecker instance.
        if not isinstance(permission_service, PermissionChecker):
            raise TypeError("PERMISSION_SERVICE must be PermissionChecker.")

        runner_config = AbilityRunnerConfig(
            hitl_timeout=self._config.ability_runner.hitl_timeout,
            default_ability_timeout=self._config.ability_runner.default_ability_timeout,
        )
        self._runner = AbilityRunner(
            hitl_notary=notary,
            permission_checker=permission_service,
            config=runner_config,
            sandbox_executor=sandbox,
            workspace=workspace,
            # 鸭子适配：AbilityRunner 期望 SubjectEventBus（await emit），本体零改动
            event_bus=_CtxEventBusAdapter(ctx),  # type: ignore[arg-type]
        )
        # AbilityExecutor Protocol declares execute_ability → dict[str, Any],
        # but the concrete AbilityRunner returns ActionResult. The unit's
        # handle_command unwraps ActionResult into a plain dict before returning
        # to the dispatcher, so the wire contract is satisfied. Consumers
        # requiring the Protocol should call through the unit (dispatch path)
        # rather than .execute_ability() directly. S2.3/S2.4 may unify this.
        ctx.provide(ABILITY_EXECUTOR.name, self._runner)

    async def stop(self) -> None:
        # AbilityRunner 本身不持有需显式停止的资源（HITLNotary 归 hitl_notary unit）。
        pass

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        if command != "execute_ability":
            return {"success": False, "error": f"Unknown ability command: {command}"}

        request_id = payload.get("request_id", "") or cmd_ctx.request_id or ""
        agent_name = payload.get("agent_name", "")
        ability_name = payload.get("ability_name", "")
        tool_args = payload.get("tool_args", {}) or {}

        result = await self.service.execute_ability(
            ability_name=ability_name,
            tool_args=tool_args,
            agent_name=agent_name,
        )

        return {
            "request_id": request_id,
            "agent_name": agent_name,
            "ability_name": ability_name,
            "success": result.outcome == ActionOutcome.SUCCESS,
            "result": result.data,
            "error": result.data.get("error") if result.outcome == ActionOutcome.FAILURE else None,
        }
