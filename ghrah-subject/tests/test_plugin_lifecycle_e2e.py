# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件生命周期端到端测试：崩溃 → failed 回执 + plugin_crashed 广播 +
owner 清理 + Unknown 兜底 + plugin_negotiated 重协商信号。

全链真实 Context + 装配链（mount_enabled_plugins）；不依赖 fiber 状态
迁移断言（listener 运行期异常不迁移 fiber 状态，r2 修正语义）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ghrah.plugin.assembly import PluginAssembly
from ghrah.plugin.loader import DiscoveredPlugin
from ghrah.plugin.spec import PluginSpec
from ouroboros import Context  # type: ignore[import-untyped]

from ghrah.subject.config import PluginTrustConfig, SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_dynamic_unit
from ghrah.subject.runtime.plugin_mount import (
    PluginSessionState,
    mount_enabled_plugins,
)
from ghrah.subject.runtime.plugin_session import PluginSession
from ghrah.subject.runtime.route_registry import UnitRouteRegistry
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class _CrashyPluginUnit(SubjectUnit):
    """含崩溃 handler 的 fake 插件 unit。"""

    def __init__(self) -> None:
        self._meta = UnitMeta(name="crashy", routes=RouteSpec(commands=frozenset({"crashy_boom"})))

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        if command == "crashy_boom":
            raise RuntimeError("boom in handler")
        return {"success": True}


@dataclass
class _FakeBus:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        self.events.append((event_type, payload))
        return 1


async def test_plugin_crash_full_lifecycle() -> None:
    """崩溃五步：挂载 → 崩溃回执 → plugin_crashed 广播 → owner 清理 →
    plugin_negotiated 随卸载广播。"""
    spec = PluginSpec(
        plugin_id="crashy",
        version="0.1.0",
        timeout_ms=2000,
        provides={"commands": ["crashy_boom"]},
    )
    discovered = [
        DiscoveredPlugin(
            spec=spec, entry_point_name="crashy", dist_name=None, unit_factory=_CrashyPluginUnit
        )
    ]
    config = SubjectConfig()
    config._plugin_trust = PluginTrustConfig(discoverable=["crashy"])  # noqa: SLF001

    bus = _FakeBus()
    async with Context() as ctx:
        ctx.provide("observer_event_bus", bus)
        registry = UnitRouteRegistry()
        state = PluginSessionState()
        session = PluginSession(state)
        fibers: dict[str, Any] = {}
        await mount_dynamic_unit(ctx, session, fibers, route_registry=registry)

        report = await mount_enabled_plugins(
            ctx,
            config,
            discovered=discovered,
            assemblies=[("p1", PluginAssembly(enabled=["crashy"]))],
            route_registry=registry,
            fibers=fibers,
            state=state,
            session=session,
        )
        assert [o.status for o in report.outcomes] == ["mounted"]
        # 挂载成功的协商广播
        assert bus.events == [("plugin_negotiated", {"changed": ["crashy"]})]
        bus.events.clear()

        # 1. 崩溃命令 → failed 回执（error 含 plugin_id 与命令语义）
        result = await bridge_command(ctx, "crashy_boom", {})
        assert result["success"] is False
        assert "plugin crashed: crashy" in result["error"]
        assert "RuntimeError: boom in handler" in result["error"]

        # 2. plugin_crashed 广播（plugin_id/command/error 摘要）
        crashed = [e for e in bus.events if e[0] == "plugin_crashed"]
        assert len(crashed) == 1
        payload = crashed[0][1]
        assert payload["plugin_id"] == "crashy"
        assert payload["command"] == "crashy_boom"
        assert "boom in handler" in payload["error"]

        # 3. owner 表已清 + 后续命令不再路由到死插件
        assert registry.owner_of("crashy_boom") is None
        unknown = await bridge_command(ctx, "crashy_boom", {})
        assert unknown == {"success": False, "error": "Unknown command: crashy_boom"}

        # 4. 协商状态清单已移除
        assert "crashy" not in state.specs

        # 5. plugin_negotiated 随卸载广播（插件死了清单变了）
        negotiated = [e for e in bus.events if e[0] == "plugin_negotiated"]
        assert negotiated == [("plugin_negotiated", {"changed": ["crashy"]})]
