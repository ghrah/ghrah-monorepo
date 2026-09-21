# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""owner 表接线测试：插件互斥裁决（挂期爆炸含 owner 名）、事件多订阅共存、
builtin 登记不互斥（serial 穿透现状回归）、exclusive 直挂探针。"""

from __future__ import annotations

from typing import Any

import pytest
from ghrah.plugin.errors import PluginMountError
from ghrah.plugin.spec import PluginSpec
from ouroboros import Context, ExclusiveListenerError  # type: ignore[import-untyped]

from ghrah.subject.runtime.ouroboros_bridge import (
    bridge_command,
    mount_dynamic_unit,
    mount_unit,
    unmount_unit,
)
from ghrah.subject.runtime.route_registry import UnitRouteRegistry
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class _FakeUnit(SubjectUnit):
    """最小 unit：命令集可参数化。"""

    def __init__(
        self, name: str, commands: frozenset[str], events: frozenset[str] = frozenset()
    ) -> None:
        self._meta = UnitMeta(name=name, routes=RouteSpec(commands=commands, events=events))

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        return {"success": True, "data": {"unit": self._meta.name}}


async def test_plugin_mount_duplicate_command_raises_at_mount_time() -> None:
    """插件路径同名命令二次挂载 → 挂期爆炸，消息含现任 owner 名（验收①）。"""
    registry = UnitRouteRegistry()
    async with Context() as ctx:
        fibers: dict[str, Any] = {}
        await mount_dynamic_unit(
            ctx,
            _FakeUnit("plugin-a", frozenset({"foo"})),
            fibers,
            route_registry=registry,
            exclusive=True,
        )
        assert registry.owner_of("foo") == "plugin-a"

        with pytest.raises(PluginMountError) as excinfo:
            await mount_dynamic_unit(
                ctx,
                _FakeUnit("plugin-b", frozenset({"foo"})),
                fibers,
                route_registry=registry,
                exclusive=True,
            )
        assert "command 'foo' already owned by unit 'plugin-a'" in str(excinfo.value)
        # 爆炸后 plugin-b 未登记
        assert registry.owner_of("foo") == "plugin-a"


async def test_plugin_mount_against_builtin_owner_raises() -> None:
    """插件命令撞 builtin 登记名 → 拒（插件侧单向互斥）。"""
    registry = UnitRouteRegistry()
    registry.register_builtin("builtin-x", frozenset({"spawn_agent"}))
    async with Context() as ctx:
        fibers: dict[str, Any] = {}
        with pytest.raises(PluginMountError) as excinfo:
            await mount_dynamic_unit(
                ctx,
                _FakeUnit("plugin-c", frozenset({"spawn_agent"})),
                fibers,
                route_registry=registry,
                exclusive=True,
            )
        assert "already owned by unit 'builtin-x'" in str(excinfo.value)


async def test_event_multi_subscriber_coexistence_with_dual_prefix() -> None:
    """两 unit 同事件 event/<t> + core:<t> 双注册互不干扰（验收②）。"""
    received: list[str] = []

    class _ListenerUnit(SubjectUnit):
        def __init__(self, name: str) -> None:
            self._meta = UnitMeta(name=name, routes=RouteSpec(events=frozenset({"agent_spawned"})))

        @property
        def meta(self) -> UnitMeta:
            return self._meta

        async def handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
            received.append(f"{self._meta.name}:{event_type}")

    async with Context() as ctx:
        fibers: dict[str, Any] = {}
        await mount_dynamic_unit(ctx, _ListenerUnit("listener-a"), fibers)
        await mount_dynamic_unit(ctx, _ListenerUnit("listener-b"), fibers)

        # 直挂路径不经过 owner 表（事件多租户合法），此处只验证双前缀分发共存
        ctx.emit("event/agent_spawned", {"n": 1})
        ctx.emit("core:agent_spawned", {"n": 1})
        # 让 emit 调度的 listener task 收敛
        from ouroboros import FiberState  # type: ignore[import-untyped]

        del FiberState
        import asyncio

        await asyncio.sleep(0.05)
        assert sorted(received) == [
            "listener-a:agent_spawned",
            "listener-a:agent_spawned",
            "listener-b:agent_spawned",
            "listener-b:agent_spawned",
        ]


async def test_builtin_style_registration_coexists() -> None:
    """两个 builtin 式（exclusive=False）同名注册共存 + serial 穿透（回归）。"""
    registry = UnitRouteRegistry()
    async with Context() as ctx:
        fibers: dict[str, Any] = {}
        await mount_dynamic_unit(
            ctx,
            _FakeUnit("core_cluster", frozenset({"list_agents"})),
            fibers,
            route_registry=registry,
        )
        await mount_dynamic_unit(
            ctx,
            _FakeUnit("core", frozenset({"list_agents"})),
            fibers,
            route_registry=registry,
        )
        # 首个非 None 短路胜出（serial 穿透）
        result = await bridge_command(ctx, "list_agents", {})
        assert result == {"success": True, "data": {"unit": "core_cluster"}}


async def test_unmount_clears_route_registry() -> None:
    """unmount 同步清理 owner 登记（防热重载残留）。"""
    registry = UnitRouteRegistry()
    async with Context() as ctx:
        fibers: dict[str, Any] = {}
        await mount_dynamic_unit(
            ctx, _FakeUnit("plugin-d", frozenset({"bar"})), fibers, route_registry=registry
        )
        assert registry.owner_of("bar") == "plugin-d"
        await unmount_unit(fibers, "plugin-d", route_registry=registry)
        assert registry.owner_of("bar") is None
        # 卸载后可重挂
        await mount_dynamic_unit(
            ctx, _FakeUnit("plugin-d", frozenset({"bar"})), fibers, route_registry=registry
        )
        assert registry.owner_of("bar") == "plugin-d"


async def test_exclusive_direct_registration_conflict() -> None:
    """直挂 ctx.on(exclusive=True) 撞插件 exclusive 注册 → ExclusiveListenerError（验收④）。"""
    registry = UnitRouteRegistry()
    spec = PluginSpec(plugin_id="test-plugin", version="0.1.0")
    async with Context() as ctx:
        fibers: dict[str, Any] = {}
        await mount_dynamic_unit(
            ctx,
            _FakeUnit("test-plugin", frozenset({"exclusive_cmd"})),
            fibers,
            route_registry=registry,
            exclusive=True,
            plugin_spec=spec,
            on_crash=_noop_crash,
        )

        async def second_handler(payload: dict[str, Any]) -> dict[str, Any]:
            return {"success": True}

        with pytest.raises(ExclusiveListenerError):
            ctx.on("command/exclusive_cmd", second_handler, exclusive=True)

        # 反向：第三方先直挂 exclusive，插件后挂 → ctx.on 处抛 ExclusiveListenerError
        # （fiber 内 apply 异常经 await_ 上抛；挂载期零残留）
        async def first_handler(payload: dict[str, Any]) -> dict[str, Any]:
            return None  # type: ignore[return-value]

        ctx.on("command/preempted_cmd", first_handler, exclusive=True)

        preemptor_fiber = ctx.plugin(
            mount_unit(
                _FakeUnit("preemptor", frozenset({"preempted_cmd"})),
                route_registry=registry,
                exclusive=True,
            )
        )
        with pytest.raises(ExclusiveListenerError):
            await preemptor_fiber.await_()
        # 挂载失败不留 owner 残留（否则会阻挡后续挂载）
        assert registry.owner_of("preempted_cmd") is None


async def test_failed_exclusive_mount_leaves_no_owner_residue() -> None:
    """ctx.on exclusive 撞车导致挂载失败 → owner 表零残留（可被后续 unit 认领）。"""
    registry = UnitRouteRegistry()
    async with Context() as ctx:
        fibers: dict[str, Any] = {}

        async def direct(payload: dict[str, Any]) -> dict[str, Any]:
            return {"success": True}

        ctx.on("command/contested", direct)  # 非 exclusive 直挂
        with pytest.raises(ExclusiveListenerError):
            await mount_dynamic_unit(
                ctx,
                _FakeUnit("loser", frozenset({"contested"})),
                fibers,
                route_registry=registry,
                exclusive=True,
            )
        assert registry.owner_of("contested") is None
        assert fibers == {}
        # 残留清除后，另一个 unit 可正常认领
        await mount_dynamic_unit(
            ctx,
            _FakeUnit("winner", frozenset({"contested"})),
            fibers,
            route_registry=registry,
        )
        assert registry.owner_of("contested") == "winner"


async def _noop_crash(plugin_id: str, command: str, error: str) -> None:
    pass
