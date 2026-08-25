# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ouroboros mounting helpers for migrated Subject units (Phase 2).

阶段 2 过渡挂载助手（阶段 3.2/4 随装配层定形后精简）：

- ``mount_unit(unit)`` 把已原生化（``ctx.provide``/``ctx.get``/``ctx.emit``/
  ``ctx.on``）的 ``SubjectUnit`` 包装为 Ouroboros plugin：``inject`` 从
  ``unit.meta.requires`` 派生；apply 内 init → 路由注册 → start；disposer
  触发 ``await unit.stop()``，服务/路由随 fiber dispose 自动撤销。
- ``bridge_command`` 经 ``ctx.serial`` 路由命令，零 handler 时返回
  ``Unknown command`` 兜底（对齐 ``MessageDispatcher`` 文案）。
- ``wait_active`` 等 fiber 收敛且 state 达 ACTIVE：``fiber.await_()`` 只等
  lifecycle task 结束，state 迁移可能在随后一个事件循环 tick 生效（实测
  2026-08-25），故 ACTIVE 判定前需轮询。

事件命名约定（emit 与 on 两端一致）：命令 ``command/<name>``、事件
``event/<常量>``。listener 签名为 ``(payload)`` 单参（试点实测结论）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from ouroboros import FiberState  # type: ignore[import-untyped]

from ghrah.subject.unit.base import CommandContext, SubjectUnit

if TYPE_CHECKING:
    from ouroboros import Context, Fiber

__all__ = [
    "bridge_command",
    "mount_unit",
    "wait_active",
]


async def wait_active(fiber: Fiber, *, timeout: float = 2.0) -> None:
    """Await a fiber and poll until it reports ACTIVE (or fail).

    统一 ``asyncio.wait_for`` 超时——inject 名单错导致 PENDING 死等时表现为
    失败而非挂起。
    """

    await asyncio.wait_for(fiber.await_(), timeout=timeout)
    deadline = asyncio.get_running_loop().time() + timeout
    while fiber.state is not FiberState.ACTIVE:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"fiber did not reach ACTIVE within {timeout}s: {fiber.state}")
        await asyncio.sleep(0.01)


def mount_unit(
    unit: SubjectUnit,
    *,
    inject: Sequence[str] | None = None,
) -> Callable[..., Awaitable[Callable[[], Awaitable[None]]]]:
    """Wrap an Ouroboros-native SubjectUnit as an Ouroboros plugin (apply).

    ``inject`` 默认从 ``unit.meta.requires`` 派生（``[key.name for key in
    requires]``）；空 requires → 空 inject（无依赖，立即 ACTIVE）。apply 内
    配置不透传——原生 unit 的配置在构造期注入（``unit._config``）。
    """

    if inject is None:
        inject = [key.name for key in unit.meta.requires]

    async def apply(ctx: Context, config: Any) -> Callable[[], Awaitable[None]]:
        del config  # 原生 unit 的配置在构造期注入（unit._config）
        await unit.init(ctx)
        _register_routes(ctx, unit)
        await unit.start()

        async def disposer() -> None:
            await unit.stop()

        return disposer

    apply.inject = list(inject)  # type: ignore[attr-defined]
    return apply


def _register_routes(ctx: Context, unit: SubjectUnit) -> None:
    """Bind a unit's declared routes onto the Ouroboros event system.

    命令/事件 handler 签名均为 ``(payload)`` 单参（试点实测 2026-08-24：
    双参会抛 TypeError）。试点期用固定 ``CommandContext.internal()`` 占位；
    ``request_id``/``session_id`` 透传归阶段 3 装配层。长跑命令合并为普通
    命令处理，优化留阶段 2/3。
    """

    routes = unit.meta.routes
    cmd_ctx = CommandContext.internal()

    for command in routes.commands:
        ctx.on(
            f"command/{command}",
            _make_command_handler(unit, command, cmd_ctx),
        )
    for command in routes.long_running_commands:
        ctx.on(
            f"command/{command}",
            _make_command_handler(unit, command, cmd_ctx),
        )
    for event_type in routes.events:
        ctx.on(
            f"event/{event_type}",
            _make_event_handler(unit, event_type),
        )


def _make_command_handler(
    unit: SubjectUnit,
    command: str,
    cmd_ctx: CommandContext,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    async def handler(payload: dict[str, Any]) -> dict[str, Any]:
        return await unit.handle_command(command, payload, cmd_ctx)

    return handler


def _make_event_handler(
    unit: SubjectUnit,
    event_type: str,
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    async def handler(payload: dict[str, Any]) -> None:
        await unit.handle_event(event_type, payload)

    return handler


async def bridge_command(
    ctx: Context,
    name: str,
    payload: dict[str, Any],
    cmd_ctx: CommandContext | None = None,
) -> dict[str, Any]:
    """Route a command via Ouroboros ``ctx.serial`` with Unknown fallback.

    ``cmd_ctx`` 在阶段 2 仅作占位透传（Ouroboros listener 单参签名不携带
    元数据）；正式的 ``request_id``/``session_id`` 透传在阶段 3 装配层实现。
    零 handler 时 ``ctx.serial`` 返回 None（实测），本助手转
    ``{"success": False, "error": f"Unknown command: {name}"}`` 对齐
    ``MessageDispatcher.dispatch_observer_command`` 的兜底文案。
    """

    result = await ctx.serial(f"command/{name}", payload)
    if result is None:
        return {"success": False, "error": f"Unknown command: {name}"}
    if not isinstance(result, dict):
        return {"success": False, "error": f"Unexpected command result for {name}"}
    return dict(result)
