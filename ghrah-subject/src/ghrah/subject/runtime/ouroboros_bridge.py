# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ouroboros adapter bridge for legacy Subject units.

试点期（上位计划 `1787015082781` 阶段 1）桥接层：把 ghrah 风格
``SubjectUnit``（``init``/``start``/``stop`` 生命周期 + ``meta.routes`` 声明）
包装为 Ouroboros plugin，在 Ouroboros ``Context`` 上挂载、提供服务、路由命令，
并在 fiber dispose 后自动撤销服务与路由。

本桥为「试点一次性桥」：不继承、不全实现 ``SubjectContext``，仅实现 workspace /
sandbox 试点 unit 触达的子集（``config`` / ``services`` / ``event_bus``）。
阶段 2 改各 unit 类本体直接用 ``ctx.provide`` / ``ctx.on`` 时，本桥即拆除。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.service_keys import SubjectServiceKey
from ghrah.subject.unit.base import CommandContext, SubjectUnit

if TYPE_CHECKING:
    from ouroboros import Context  # type: ignore[import-untyped]

__all__ = [
    "BridgeSubjectContext",
    "bridge_command",
    "unit_to_plugin",
]


class _BridgeServices:
    """Minimal ``SubjectServices``-shaped adapter backed by Ouroboros provide/get.

    ``set(key, v)`` → ``ctx.provide(key.name, v)``（plugin fiber 内有效，随
    fiber dispose 撤销）。
    ``require(key)`` → ``ctx.get(key.name, strict=True)``，捕获 Ouroboros
    ``AttributeError`` 并转 ``RuntimeError`` 以对齐 ``SubjectServices.require``
    文案。
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def set(self, key: SubjectServiceKey[Any], value: Any) -> None:
        self._ctx.provide(key.name, value)

    def get(self, key: SubjectServiceKey[Any], default: Any = None) -> Any:
        return self._ctx.get(key.name, strict=False) or default

    def require(self, key: SubjectServiceKey[Any]) -> Any:
        try:
            return self._ctx.get(key.name, strict=True)
        except AttributeError as error:  # Ouroboros 缺服务抛 AttributeError
            raise RuntimeError(
                f"Required subject service '{key.name}' is not set."
            ) from error


class _BridgeEventBus:
    """Minimal ``SubjectEventBus``-shaped adapter backed by Ouroboros ``emit``.

    Ouroboros ``ctx.emit`` 是同步的；本桥的 ``emit`` 保留 async 签名以兼容
    ``SubjectEventBus.emit``（调用方 ``await ctx.event_bus.emit(...)``），实现
    内同步转发。``subscribe`` 等 workspace/sandbox 试点不触达的面抛
    NotImplementedError，阶段 2 按 unit 增量补全或随类本体改造拆除。
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    async def emit(self, event_type: str, payload: Any) -> None:
        self._ctx.emit(event_type, payload)

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "BridgeEventBus.subscribe is not supported in the Ouroboros pilot; "
            "the unit under migration must not require it."
        )


class BridgeSubjectContext:
    """Duck-typed minimal SubjectContext for the Ouroboros pilot.

    仅实现 workspace/sandbox 试点 unit 触达的面：``config``、``services``、
    ``event_bus``。不实现 ``engine``/``dispatcher``/``units``/``get_unit``/
    ``create_task``/``observer_endpoint``/``capability_registry``——试点 unit
    不触达，触达即 NotImplementedError 显式暴露（阶段 2 增量处理）。
    """

    def __init__(self, ctx: Context, config: SubjectConfig) -> None:
        self._ctx = ctx
        self._config = config
        self._services = _BridgeServices(ctx)
        self._event_bus = _BridgeEventBus(ctx)

    @property
    def config(self) -> SubjectConfig:
        return self._config

    @property
    def services(self) -> _BridgeServices:
        return self._services

    @property
    def event_bus(self) -> _BridgeEventBus:
        return self._event_bus


def unit_to_plugin(
    unit: SubjectUnit,
    *,
    inject: Sequence[str] | Mapping[str, Any] | None = None,
) -> Callable[..., Awaitable[Callable[[], Awaitable[None]]]]:
    """Wrap a legacy SubjectUnit as an Ouroboros plugin (apply function).

    ``inject`` 默认从 ``unit.meta.requires`` 派生（``[key.name for key in
    requires]``）；可显式覆盖。空 requires → 空 inject（无依赖，立即 ACTIVE）。

    apply 内：构造 ``BridgeSubjectContext`` → ``await unit.init(bridge)`` →
    按声明路由注册 ``ctx.on("command/<c>", ...)`` / ``ctx.on("event/<e>", ...)``
    → ``await unit.start()`` → 返回 async disposer（``await unit.stop()``），
    随 fiber dispose 触发，停止 unit 并撤销其 provide/on 注册。
    """

    if inject is None:
        inject = [key.name for key in unit.meta.requires]

    async def apply(ctx: Context, config: Any) -> Callable[[], Awaitable[None]]:
        subject_config = config if isinstance(config, SubjectConfig) else getattr(
            unit, "_config", None
        )
        if subject_config is None:
            raise TypeError(
                "unit_to_plugin requires a SubjectConfig via plugin config or "
                "unit._config; neither was available."
            )
        bridge = BridgeSubjectContext(ctx, subject_config)

        await unit.init(bridge)
        _register_routes(ctx, unit)
        await unit.start()

        async def disposer() -> None:
            await unit.stop()

        return disposer

    apply.inject = inject  # type: ignore[attr-defined]
    return apply


def _register_routes(ctx: Context, unit: SubjectUnit) -> None:
    """Bind a unit's declared routes onto the Ouroboros event system.

    命令 handler 签名为 ``(payload)`` 单参（实测 2026-08-24：双参会抛
    TypeError）。试点期用固定 ``CommandContext.internal()`` 占位；``request_id``
    /``session_id`` 透传归阶段 3 装配层。事件 handler 同为单参 ``(payload)``。
    长跑命令在试点合并为普通命令处理，优化留阶段 2/3。
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

    ``cmd_ctx`` 在试点期仅作占位透传（Ouroboros listener 单参签名不携带元数据）；
    正式的 ``request_id``/``session_id`` 透传在阶段 3 装配层实现。零 handler 时
    ``ctx.serial`` 返回 None（实测），本助手转 ``{"success": False, "error":
    f"Unknown command: {name}"}`` 对齐 ``MessageDispatcher.dispatch_observer_command``
    的兜底文案。
    """

    result = await ctx.serial(f"command/{name}", payload)
    if result is None:
        return {"success": False, "error": f"Unknown command: {name}"}
    if not isinstance(result, dict):
        return {"success": False, "error": f"Unexpected command result for {name}"}
    return dict(result)
