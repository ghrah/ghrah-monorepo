# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""PluginSession 双重触发协商测试：连接级 responder（三态回执）、变更级
广播（fake bus）、bus 缺失降级、两路共用 negotiate 纯函数。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ghrah.plugin.negotiator import TsHalfReport, negotiate, python_half_from_spec
from ghrah.plugin.spec import PluginSpec
from ouroboros import Context  # type: ignore[import-untyped]

from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_dynamic_unit
from ghrah.subject.runtime.plugin_mount import PluginSessionState
from ghrah.subject.runtime.plugin_session import PluginSession
from ghrah.subject.runtime.route_registry import UnitRouteRegistry


@dataclass
class _FakeBus:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        self.events.append((event_type, payload))
        return 1


def _spec(plugin_id: str, version: str = "0.1.0") -> PluginSpec:
    return PluginSpec(
        plugin_id=plugin_id,
        version=version,
        provides={"capabilities": [f"{plugin_id}:attr"]},
        requires={"capabilities": ["other:dep"]},
    )


async def _mounted_session(ctx: Any, bus: Any = None) -> tuple[PluginSession, PluginSessionState]:
    state = PluginSessionState()
    session = PluginSession(state)
    fibers: dict[str, Any] = {}
    await mount_dynamic_unit(ctx, session, fibers, route_registry=UnitRouteRegistry())
    if bus is not None:
        ctx.provide("observer_event_bus", bus)
    return session, state


async def test_connection_level_responder_matched_python_only_conflict() -> None:
    """三态回执：matched / python_only / version_conflicts。"""
    spec_a = _spec("plugin-a")
    spec_b = _spec("plugin-b", version="0.2.0")
    async with Context() as ctx:
        session, state = await _mounted_session(ctx)
        state.specs["plugin-a"] = spec_a
        state.specs["plugin-b"] = spec_b

        result = await bridge_command(
            ctx,
            "plugin_negotiate",
            {
                "enabled_ts": [
                    {"plugin_id": "plugin-a", "version": "0.1.0"},
                    {"plugin_id": "plugin-b", "version": "0.9.9"},
                    {"plugin_id": "plugin-c", "version": "1.0.0"},
                ]
            },
        )
        assert result["success"] is True
        data = result["data"]
        assert [m["plugin_id"] for m in data["matched"]] == ["plugin-a"]
        # b 双侧在场但版本冲突 → version_conflicts（非 python_only）
        assert data["python_only"] == []
        assert [t["plugin_id"] for t in data["ts_only"]] == ["plugin-c"]
        assert data["version_conflicts"] == [
            {
                "plugin_id": "plugin-b",
                "python_version": "0.2.0",
                "ts_version": "0.9.9",
            }
        ]
        # python 侧 requires 缺失 → missing_capabilities
        assert data["missing_capabilities"] == ["other:dep"]


async def test_invalid_payload_returns_error_receipt() -> None:
    async with Context() as ctx:
        await _mounted_session(ctx)
        result = await bridge_command(ctx, "plugin_negotiate", {"enabled_ts": "not-a-list"})
        assert result["success"] is False
        assert "invalid plugin_negotiate payload" in result["error"]


async def test_change_level_broadcast_via_bus() -> None:
    bus = _FakeBus()
    async with Context() as ctx:
        session, _ = await _mounted_session(ctx, bus)
        await session.broadcast_negotiated(["plugin-a", "plugin-b"])
        assert bus.events == [("plugin_negotiated", {"changed": ["plugin-a", "plugin-b"]})]


async def test_broadcast_without_bus_degrades_to_log() -> None:
    async with Context() as ctx:
        session, _ = await _mounted_session(ctx)  # 无 bus
        await session.broadcast_negotiated(["x"])  # 不炸
        await session.publish_event("plugin_crashed", {"plugin_id": "x"})  # 不炸


async def test_both_paths_share_negotiate_pure_function() -> None:
    """两路共用同一 negotiate 纯函数：同输入同输出。"""
    spec_a = _spec("plugin-a")
    ts = [TsHalfReport(plugin_id="plugin-a", version="0.1.0")]
    snapshot = [python_half_from_spec(spec_a)]
    direct = negotiate(python=snapshot, ts=ts)

    async with Context() as ctx:
        session, state = await _mounted_session(ctx)
        state.specs["plugin-a"] = spec_a
        result = await bridge_command(
            ctx, "plugin_negotiate", {"enabled_ts": [t.model_dump() for t in ts]}
        )
        assert result["data"] == direct.model_dump()


async def test_owner_registry_records_session_command() -> None:
    """plugin_negotiate 走 builtin 式登记（owner 表可查）。"""
    registry = UnitRouteRegistry()
    state = PluginSessionState()
    session = PluginSession(state)
    fibers: dict[str, Any] = {}
    async with Context() as ctx:
        await mount_dynamic_unit(ctx, session, fibers, route_registry=registry)
        assert registry.owner_of("plugin_negotiate") == "plugin_session"
