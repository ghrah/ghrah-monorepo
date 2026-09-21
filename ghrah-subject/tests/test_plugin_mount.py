# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件装配链测试：信任闸/装配闸双层、装配排序、multi_instance 拒挂、
spec-only 不挂载、撞 builtin 命令拒、协商状态登记。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ghrah.plugin.assembly import PluginAssembly
from ghrah.plugin.loader import DiscoveredPlugin
from ghrah.plugin.spec import PluginSpec
from ouroboros import Context  # type: ignore[import-untyped]

from ghrah.subject.config import PluginTrustConfig, SubjectConfig
from ghrah.subject.runtime.plugin_mount import (
    PluginSessionState,
    mount_enabled_plugins,
)
from ghrah.subject.runtime.plugin_session import PluginSession
from ghrah.subject.runtime.route_registry import UnitRouteRegistry
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class _PluginUnit(SubjectUnit):
    """最小插件 unit：命令名 = plugin_id + '_run'。"""

    def __init__(self, plugin_id: str) -> None:
        self._meta = UnitMeta(
            name=plugin_id, routes=RouteSpec(commands=frozenset({f"{plugin_id}_run"}))
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        return {"success": True, "data": {"plugin": self._meta.name}}


@dataclass
class _FakeBus:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        self.events.append((event_type, payload))
        return 1


def _discovered(*specs: PluginSpec, unit_factory: bool = True) -> list[DiscoveredPlugin]:
    out = []
    for spec in specs:
        factory = (lambda s=spec: _PluginUnit(s.plugin_id)) if unit_factory else None
        out.append(
            DiscoveredPlugin(
                spec=spec, entry_point_name=spec.plugin_id, dist_name=None, unit_factory=factory
            )
        )
    return out


def _spec(plugin_id: str, **kwargs: Any) -> PluginSpec:
    return PluginSpec(plugin_id=plugin_id, version="0.1.0", **kwargs)


def _config(trust: list[str]) -> SubjectConfig:
    config = SubjectConfig()
    config._plugin_trust = PluginTrustConfig(discoverable=trust)  # noqa: SLF001
    return config


async def _mount(
    ctx,
    discovered,
    assemblies,
    trust,
    route_registry=None,
    bus=None,
):
    route_registry = route_registry or UnitRouteRegistry()
    state = PluginSessionState()
    session = PluginSession(state)
    fibers: dict[str, Any] = {}
    from ghrah.subject.runtime.ouroboros_bridge import mount_dynamic_unit

    await mount_dynamic_unit(ctx, session, fibers, route_registry=route_registry)
    if bus is not None:
        ctx.provide("observer_event_bus", bus)
    report = await mount_enabled_plugins(
        ctx,
        _config(trust),
        discovered=discovered,
        assemblies=assemblies,
        route_registry=route_registry,
        fibers=fibers,
        state=state,
        session=session,
    )
    return report, state, fibers, route_registry, session


async def test_trust_gate_rejects_untrusted() -> None:
    """信任闸：不在 trust 清单 → 拒（含跳闸直接 Project 声明场景）。"""
    spec_a, spec_b = _spec("plugin-a"), _spec("plugin-b")
    discovered = _discovered(spec_a, spec_b)
    async with Context() as ctx:
        report, state, fibers, _, _ = await _mount(
            ctx,
            discovered,
            [("p1", PluginAssembly(enabled=["plugin-a", "plugin-b"]))],
            trust=["plugin-a"],  # b 未信任
        )
        statuses = {o.plugin_id: o.status for o in report.outcomes}
        assert statuses["plugin-a"] == "mounted"
        assert statuses["plugin-b"] == "not_trusted"
        assert "plugin-b" not in state.specs
        assert "plugin-b" not in fibers


async def test_not_discovered_reported_not_fatal() -> None:
    async with Context() as ctx:
        report, _, fibers, _, _ = await _mount(
            ctx, _discovered(), [("p1", PluginAssembly(enabled=["ghost"]))], trust=["ghost"]
        )
        assert report.outcomes[0].status == "not_discovered"
        assert fibers_keys_excl_session(fibers) == []


def fibers_keys_excl_session(fibers: dict[str, Any]) -> list[str]:
    return [k for k in fibers if k != "plugin_session"]


async def test_after_sorting_applies() -> None:
    """装配排序：enabled 序 [b, a] + b after a → 挂载序 a 先（观察 report 挂载序）。"""
    spec_a = _spec("plugin-a")
    spec_b = _spec("plugin-b", after=["plugin-a"])

    discovered = _discovered(spec_a, spec_b)
    async with Context() as ctx:
        report, state, _, registry, _ = await _mount(
            ctx,
            discovered,
            [("p1", PluginAssembly(enabled=["plugin-b", "plugin-a"]))],
            trust=["plugin-a", "plugin-b"],
        )
        # report 中 mounted 项顺序 = 挂载顺序
        mount_order = [o.plugin_id for o in report.outcomes if o.status == "mounted"]
        assert mount_order == ["plugin-a", "plugin-b"]
        assert set(state.specs) == {"plugin-a", "plugin-b"}
        assert registry.owner_of("plugin-a_run") == "plugin-a"


async def test_multi_instance_rejected() -> None:
    spec = _spec("fanout", multi_instance=True)
    assembly = PluginAssembly(enabled=["fanout"], instances={"fanout": {"i1": {"enabled": True}}})
    async with Context() as ctx:
        report, state, fibers, _, _ = await _mount(
            ctx,
            _discovered(spec),
            [("p1", assembly)],
            trust=["fanout"],
        )
        outcome = report.outcomes[0]
        assert outcome.status == "multi_instance_unsupported"
        assert "instance expansion" in outcome.detail
        assert "fanout" not in state.specs
        assert fibers_keys_excl_session(fibers) == []


async def test_multi_instance_missing_instances_invalid() -> None:
    """multi_instance 缺 instances → invalid_assembly（先于 multi_instance 拒挂）。"""
    spec = _spec("fanout", multi_instance=True)
    async with Context() as ctx:
        report, _, _, _, _ = await _mount(
            ctx,
            _discovered(spec),
            [("p1", PluginAssembly(enabled=["fanout"]))],
            trust=["fanout"],
        )
        assert report.outcomes[0].status == "invalid_assembly"


async def test_single_instance_with_instances_invalid() -> None:
    spec = _spec("simple")
    assembly = PluginAssembly(enabled=["simple"], instances={"simple": {"x": {"enabled": True}}})
    async with Context() as ctx:
        report, _, _, _, _ = await _mount(
            ctx,
            _discovered(spec),
            [("p1", assembly)],
            trust=["simple"],
        )
        assert report.outcomes[0].status == "invalid_assembly"


async def test_spec_only_plugin_negotiable_not_mountable() -> None:
    spec = _spec("spec-only")
    async with Context() as ctx:
        report, state, fibers, _, _ = await _mount(
            ctx,
            _discovered(spec, unit_factory=False),
            [("p1", PluginAssembly(enabled=["spec-only"]))],
            trust=["spec-only"],
        )
        assert report.outcomes[0].status == "spec_only"
        assert "spec-only" not in state.specs
        assert fibers_keys_excl_session(fibers) == []


async def test_command_conflict_with_builtin_rejected() -> None:
    """单向互斥回归：插件命令撞 builtin owner → mount_failed（PluginMountError）。"""
    registry = UnitRouteRegistry()
    registry.register_builtin("builtin-x", frozenset({"probe_cmd"}))
    spec = _spec("probe")
    discovered = [
        DiscoveredPlugin(
            spec=spec,
            entry_point_name="probe",
            dist_name=None,
            unit_factory=_ProbeConflictUnit,
        )
    ]
    async with Context() as ctx:
        report, state, fibers, _, _ = await _mount(
            ctx,
            discovered,
            [("p1", PluginAssembly(enabled=["probe"]))],
            trust=["probe"],
            route_registry=registry,
        )
        outcome = report.outcomes[0]
        assert outcome.status == "mount_failed"
        assert "probe_cmd" in outcome.detail and "builtin-x" in outcome.detail
        assert "probe" not in state.specs


class _ProbeConflictUnit(SubjectUnit):
    def __init__(self) -> None:
        self._meta = UnitMeta(name="probe", routes=RouteSpec(commands=frozenset({"probe_cmd"})))

    @property
    def meta(self) -> UnitMeta:
        return self._meta


async def test_mount_success_registers_provides_and_broadcasts() -> None:
    spec = _spec(
        "toolkit",
        provides={"capabilities": ["toolkit:attr"], "commands": ["toolkit_run"]},
    )
    bus = _FakeBus()
    async with Context() as ctx:
        report, state, fibers, registry, session = await _mount(
            ctx,
            _discovered(spec),
            [("p1", PluginAssembly(enabled=["toolkit"]))],
            trust=["toolkit"],
            bus=bus,
        )
        assert report.outcomes[0].status == "mounted"
        assert state.specs["toolkit"].provides.capabilities == ["toolkit:attr"]
        # 挂载成功 → 变更级协商广播
        negotiated = [e for e in bus.events if e[0] == "plugin_negotiated"]
        assert negotiated and negotiated[0][1]["changed"] == ["toolkit"]
        # owner 表登记（插件路径 register 语义）
        assert registry.owner_of("toolkit_run") == "toolkit"
        del session


async def test_missing_project_status_defaults_to_active() -> None:
    """未提供 project_statuses 时视为 active → 正常装配。"""
    spec = _spec("default-active-plugin")
    async with Context() as ctx:
        report, state, _, _, _ = await _mount(
            ctx,
            _discovered(spec),
            [("p1", PluginAssembly(enabled=["default-active-plugin"]))],
            trust=["default-active-plugin"],
            # 不传 project_statuses：默认视为 active
        )
        assert report.outcomes[0].status == "mounted"
        assert "default-active-plugin" in state.specs


async def test_project_statuses_pause_excludes() -> None:
    spec = _spec("paused-plugin")
    route_registry = UnitRouteRegistry()
    state = PluginSessionState()
    session = PluginSession(state)
    fibers: dict[str, Any] = {}
    async with Context() as ctx:
        from ghrah.subject.runtime.ouroboros_bridge import mount_dynamic_unit

        await mount_dynamic_unit(ctx, session, fibers, route_registry=route_registry)
        report = await mount_enabled_plugins(
            ctx,
            _config(["paused-plugin"]),
            discovered=_discovered(spec),
            assemblies=[("p1", PluginAssembly(enabled=["paused-plugin"]))],
            route_registry=route_registry,
            fibers=fibers,
            state=state,
            session=session,
            project_statuses={"p1": "paused"},
        )
        assert report.outcomes == []
        assert state.specs == {}
