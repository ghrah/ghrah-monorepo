# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ouroboros mounting helpers for migrated Subject units (Phase 2).

过渡期挂载助手（装配层定形后精简）：

- ``mount_unit(unit)`` 把已原生化（``ctx.provide``/``ctx.get``/``ctx.emit``/
  ``ctx.on``）的 ``SubjectUnit`` 包装为 Ouroboros plugin：``inject`` 从
  ``unit.meta.requires`` 派生；apply 内 init → 路由注册 → start；disposer
  触发 ``await unit.stop()``，服务/路由随 fiber dispose 自动撤销。
- ``bridge_command`` 经 ``ctx.serial`` 路由命令，零 handler 时返回
  ``Unknown command`` 兜底（对齐 ``MessageDispatcher`` 文案）。
- ``wait_active`` 等 fiber 收敛且 state 达 ACTIVE：``fiber.await_()`` 只等
  lifecycle task 结束，state 迁移可能在随后一个事件循环 tick 生效（实测
  2026-08-25），故 ACTIVE 判定前需轮询。
- 插件挂载路径（``mount_unit(..., route_registry=..., exclusive=True)``）：
  命令注册传 ``exclusive=True`` 双保险 + owner 表互斥裁决（挂期爆炸）；
  命令 handler 外层包崩溃/超时 wrapper（异常 → on_crash 回调 → failed
  回执；超时按 spec ``on_timeout`` 裁决）。

事件命名约定（emit 与 on 两端一致）：命令 ``command/<name>``、事件
``event/<常量>``。listener 签名为 ``(payload)`` 单参（实测结论）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from ouroboros import FiberState  # type: ignore[import-untyped]

from ghrah.subject.unit.base import CommandContext, SubjectUnit

if TYPE_CHECKING:
    from ghrah.plugin.spec import PluginSpec
    from ouroboros import Context, Fiber

    from ghrah.subject.runtime.route_registry import UnitRouteRegistry

__all__ = [
    "bridge_command",
    "mount_dynamic_unit",
    "mount_unit",
    "unmount_unit",
    "wait_active",
]

# 插件命令崩溃回调：(plugin_id, command, error 摘要) → 卸载/清理/广播由装配层注入。
PluginCrashCallback = Callable[[str, str, str], Awaitable[None]]


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
    route_registry: UnitRouteRegistry | None = None,
    exclusive: bool = False,
    plugin_spec: PluginSpec | None = None,
    on_crash: PluginCrashCallback | None = None,
) -> Callable[..., Awaitable[Callable[[], Awaitable[None]]]]:
    """Wrap an Ouroboros-native SubjectUnit as an Ouroboros plugin (apply).

    ``inject`` 默认从 ``unit.meta.requires`` 派生（``[key.name for key in
    requires]``）；空 requires → 空 inject（无依赖，立即 ACTIVE）。apply 内
    配置不透传——原生 unit 的配置在构造期注入（``unit._config``）。

    插件路径附加参数：

    - ``route_registry``：owner 表。``exclusive=True`` 时命令互斥裁决
      （重复 → raise ``PluginMountError``，消息含现任 owner 名）+
      ``ctx.on(..., exclusive=True)`` 双保险；False/None 时仅登记
      （builtin/third_party 多实例同名共存现状零改动）。
    - ``plugin_spec``/``on_crash``：二者同时提供时命令 handler 外层包
      崩溃/超时 wrapper（异常 → on_crash 回调 → failed 回执；
      ``timeout_ms`` 超时按 ``on_timeout`` 裁决）。
    """

    if inject is None:
        inject = [key.name for key in unit.meta.requires]

    async def apply(ctx: Context, config: Any) -> Callable[[], Awaitable[None]]:
        del config  # 原生 unit 的配置在构造期注入（unit._config）
        await unit.init(ctx)
        _register_routes(
            ctx,
            unit,
            route_registry=route_registry,
            exclusive=exclusive,
            plugin_spec=plugin_spec,
            on_crash=on_crash,
        )
        await unit.start()

        async def disposer() -> None:
            await unit.stop()

        return disposer

    apply.inject = list(inject)  # type: ignore[attr-defined]
    # fiber 命名：默认 "apply" 会被 Ouroboros 归一为 None（名字回退 <root>），
    # 动态挂载多实例时冲突/错误无法区分身份——以 unit.meta.name 命名。
    apply.__name__ = unit.meta.name
    return apply


def _register_routes(
    ctx: Context,
    unit: SubjectUnit,
    *,
    route_registry: UnitRouteRegistry | None = None,
    exclusive: bool = False,
    plugin_spec: PluginSpec | None = None,
    on_crash: PluginCrashCallback | None = None,
) -> None:
    """Bind a unit's declared routes onto the Ouroboros event system.

    命令/事件 handler 签名均为 ``(payload)`` 单参（实测 2026-08-24：
    双参会抛 TypeError）。当前用固定 ``CommandContext.internal()`` 占位；
    ``request_id``/``session_id`` 透传由装配层补全。长跑命令合并为普通
    命令处理，优化留后续。

    插件路径（``exclusive=True``）：owner 表互斥裁决 + ``ctx.on`` exclusive
    透传 + 崩溃/超时 wrapper。事件订阅一律不 exclusive（多租户
    合法），owner 表登记面照记。
    """

    routes = unit.meta.routes
    cmd_ctx = CommandContext.internal()

    registered = False
    if route_registry is not None:
        commands = list(routes.commands) + list(routes.long_running_commands)
        if exclusive:
            route_registry.register(unit.meta.name, commands)
        else:
            route_registry.register_builtin(unit.meta.name, commands)
        registered = True

    plugin_mode = plugin_spec is not None and on_crash is not None
    try:
        if registered and route_registry is not None and routes.events:
            route_registry.subscribe_events(unit.meta.name, routes.events)
        for command in routes.commands:
            ctx.on(
                f"command/{command}",
                _make_command_handler(
                    unit,
                    command,
                    cmd_ctx,
                    plugin_spec=plugin_spec if plugin_mode else None,
                    on_crash=on_crash if plugin_mode else None,
                ),
                exclusive=exclusive,
            )
        for command in routes.long_running_commands:
            ctx.on(
                f"command/{command}",
                _make_command_handler(
                    unit,
                    command,
                    cmd_ctx,
                    plugin_spec=plugin_spec if plugin_mode else None,
                    on_crash=on_crash if plugin_mode else None,
                ),
                exclusive=exclusive,
            )
        for event_type in routes.events:
            handler = _make_event_handler(unit, event_type)
            ctx.on(
                f"event/{event_type}",
                handler,
            )
            # 同一事件同时绑定 core: 域：CoreUnit 实例只以 ``core:{type}`` 发射
            # （如 agent_spawned/agent_terminated），Subject 单元声明订阅这些
            # 生命周期事件时必须能收到 Core 域来源，否则接线死亡。
            ctx.on(
                f"core:{event_type}",
                handler,
            )
    except BaseException:
        # ctx.on 抛错（如撞既有 exclusive 监听）时回滚 owner 表登记，避免
        # 失败挂载留下幽灵 owner 阻挡后续挂载。
        if registered and route_registry is not None:
            route_registry.unregister(unit.meta.name)
        raise


def _make_command_handler(
    unit: SubjectUnit,
    command: str,
    cmd_ctx: CommandContext,
    *,
    plugin_spec: PluginSpec | None = None,
    on_crash: PluginCrashCallback | None = None,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    if plugin_spec is not None and on_crash is not None:
        return _make_plugin_command_handler(
            unit, command, cmd_ctx, spec=plugin_spec, on_crash=on_crash
        )

    async def handler(payload: dict[str, Any]) -> dict[str, Any]:
        return await unit.handle_command(command, payload, cmd_ctx)

    return handler


def _make_plugin_command_handler(
    unit: SubjectUnit,
    command: str,
    cmd_ctx: CommandContext,
    *,
    spec: PluginSpec,
    on_crash: PluginCrashCallback,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """插件命令 handler 外层 wrapper：超时裁决 + 崩溃路径。

    - ``asyncio.wait_for(inner, spec.timeout_ms / 1000)``；
    - ``TimeoutError``：``on_timeout == "allow_with_warn"`` → 命令结果透传
      + ``warning`` 字段；``reject``（默认）→ 走崩溃路径；
    - ``Exception`` → ``on_crash(plugin_id, command, 摘要)``（装配层注入：
      failed 标记 + 自动 unmount + owner 清理 + ``plugin_crashed`` 广播）
      → 回执 ``{"success": False, "error": "plugin crashed: ..."}``；
    - 不吞 ``asyncio.CancelledError``（宿主关闭语义）。
    """
    plugin_id = spec.plugin_id
    timeout_s = spec.timeout_ms / 1000
    allow_with_warn = spec.on_timeout == "allow_with_warn"

    async def handler(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await asyncio.wait_for(
                unit.handle_command(command, payload, cmd_ctx), timeout=timeout_s
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            if allow_with_warn:
                return {
                    "success": True,
                    "data": {},
                    "warning": f"plugin timeout after {spec.timeout_ms}ms "
                    f"(on_timeout=allow_with_warn): {plugin_id}:{command}",
                }
            summary = f"timeout after {spec.timeout_ms}ms (on_timeout=reject)"
            await on_crash(plugin_id, command, summary)
            return {"success": False, "error": f"plugin crashed: {plugin_id}: {summary}"}
        except Exception as exc:
            summary = f"{type(exc).__name__}: {exc}"
            await on_crash(plugin_id, command, summary)
            return {"success": False, "error": f"plugin crashed: {plugin_id}: {summary}"}
        return result

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

    **消歧防御约定（聚合裁决后无实际冲突面，约定仅防御第三方同名命令）**：
    ``ctx.serial`` 按注册顺序执行 listener，首个返回非 None 者短路胜出，
    返回 None 穿透给下一个 handler——即「handler 返回 None = 不是我的」。
    挂载顺序由 ``mount_builtin_units`` 列表固定：subject 单元在前、
    CoreUnit 实例经 registry 运行时挂载必然在后。全部返回 None → 本助手
    转 ``{"success": False, "error": f"Unknown command: {name}"}`` 兜底
    （对齐旧 ``MessageDispatcher.dispatch_observer_command`` 文案）。

    ``cmd_ctx`` 占位不透传（Ouroboros listener 单参签名）；``request_id``/
    ``session_id`` 由装配层注入 payload（见 server/router 适配器）。
    """

    result = await ctx.serial(f"command/{name}", payload)
    if result is None:
        return {"success": False, "error": f"Unknown command: {name}"}
    if not isinstance(result, dict):
        return {"success": False, "error": f"Unexpected command result for {name}"}
    return dict(result)


# ----------------------------------------------------------------
# 动态挂载/卸载 API（任务 6：热插拔正式面）
# ----------------------------------------------------------------


async def mount_dynamic_unit(
    ctx: Context,
    unit: SubjectUnit,
    fibers: dict[str, Fiber],
    name: str | None = None,
    *,
    timeout: float = 10.0,
    route_registry: UnitRouteRegistry | None = None,
    exclusive: bool = False,
    plugin_spec: PluginSpec | None = None,
    on_crash: PluginCrashCallback | None = None,
) -> Fiber:
    """运行时挂载一个 unit（热插拔），登记到 ``fibers`` 表。

    映射 ``ctx.plugin(mount_unit(unit))`` + ``wait_active``；首个真实
    消费者 = CoreClusterRegistry.ensure_cluster（cluster = CoreUnit 实例）。
    ``name`` 默认取 ``unit.meta.name``。插件路径附加参数透传 ``mount_unit``
    （owner 表互斥 + exclusive + 崩溃 wrapper）。

    Raises:
        ValueError: 同名 fiber 已登记（重复挂载须先 unmount）。
    """
    unit_name = name or unit.meta.name
    if unit_name in fibers:
        raise ValueError(f"unit '{unit_name}' is already mounted (unmount first).")
    fiber = ctx.plugin(
        mount_unit(
            unit,
            route_registry=route_registry,
            exclusive=exclusive,
            plugin_spec=plugin_spec,
            on_crash=on_crash,
        )
    )
    await wait_active(fiber, timeout=timeout)
    fibers[unit_name] = fiber
    return fiber


async def unmount_unit(
    fibers: dict[str, Fiber],
    name: str,
    *,
    route_registry: UnitRouteRegistry | None = None,
) -> None:
    """卸载并注销一个已挂载 unit（服务/路由随 fiber dispose 撤销）。

    未知 name 静默返回（幂等，对齐 registry.shutdown_cluster 语义）。
    ``route_registry`` 提供时同步清理 owner/订阅登记（防热重载残留）。
    """
    if route_registry is not None:
        route_registry.unregister(name)
    fiber = fibers.pop(name, None)
    if fiber is None:
        return
    await fiber.dispose()
