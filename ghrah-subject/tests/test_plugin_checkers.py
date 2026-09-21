# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""checker 装配接线测试：挂载注册、崩溃注销、unit 不在场降级。"""

from __future__ import annotations

from typing import Any

from ghrah.plugin.assembly import PluginAssembly
from ghrah.plugin.loader import DiscoveredPlugin
from ghrah.plugin.spec import PluginSpec
from ghrah.taskstore.checkers import CheckerRegistry
from ouroboros import Context  # type: ignore[import-untyped]

from ghrah.subject.config import PluginTrustConfig, SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import mount_dynamic_unit
from ghrah.subject.runtime.plugin_mount import PluginSessionState, mount_enabled_plugins
from ghrah.subject.runtime.plugin_session import PluginSession
from ghrah.subject.runtime.route_registry import UnitRouteRegistry
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class _PluginUnit(SubjectUnit):
    """最小插件 unit：命令名 = plugin_id + '_run'（崩溃由 wrapper 触发）。"""

    def __init__(self, plugin_id: str, *, boom: bool = False) -> None:
        self._meta = UnitMeta(
            name=plugin_id, routes=RouteSpec(commands=frozenset({f"{plugin_id}_run"}))
        )
        self._boom = boom

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        if self._boom:
            raise RuntimeError("plugin bug")
        return {"success": True}


def _checker(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
    return {"passed": True}


def _make_checker(name: str) -> Any:
    return _checker


def _checker_spec(plugin_id: str, checkers: list[str]) -> PluginSpec:
    return PluginSpec(
        plugin_id=plugin_id,
        version="0.1.0",
        provides={"checkers": checkers, "capabilities": [f"{plugin_id}:attr"]},
    )


def _config(trust: list[str]) -> SubjectConfig:
    config = SubjectConfig()
    config._plugin_trust = PluginTrustConfig(discoverable=trust)  # noqa: SLF001
    return config


async def _mount_with_sink(
    ctx: Any,
    *,
    spec: PluginSpec,
    unit: SubjectUnit,
    checker_factory: Any,
    registry: CheckerRegistry | None,
) -> tuple[Any, Any]:
    route_registry = UnitRouteRegistry()
    state = PluginSessionState()
    session = PluginSession(state)
    fibers: dict[str, Any] = {}
    await mount_dynamic_unit(ctx, session, fibers, route_registry=route_registry)

    discovered = [
        DiscoveredPlugin(
            spec=spec,
            entry_point_name=spec.plugin_id,
            dist_name=None,
            unit_factory=lambda u=unit: u,
            checker_factory=checker_factory,
        )
    ]

    async def sink(plugin_id: str, checkers: dict[str, Any]) -> None:
        if registry is None:
            return
        for name, checker in checkers.items():
            if checker is None:
                registry.unregister(name)
            else:
                registry.register(name, checker)

    report = await mount_enabled_plugins(
        ctx,
        _config([spec.plugin_id]),
        discovered=discovered,
        assemblies=[("p1", PluginAssembly(enabled=[spec.plugin_id]))],
        route_registry=route_registry,
        fibers=fibers,
        state=state,
        session=session,
        on_checkers=sink if registry is not None else None,
    )
    return report, (ctx, fibers, state, session, route_registry)


async def test_checker_registered_on_mount_and_resolvable() -> None:
    """挂载成功 → checker 经工厂构造并注册；内核 resolve 命中。"""
    spec = _checker_spec("checker-plugin", ["commit_in_repo", "lint_clean"])
    registry = CheckerRegistry()
    async with Context() as ctx:
        report, _ = await _mount_with_sink(
            ctx,
            spec=spec,
            unit=_PluginUnit("checker-plugin"),
            checker_factory=_make_checker,
            registry=registry,
        )
        assert report.outcomes[0].status == "mounted"
        assert registry.resolve("commit_in_repo") is not None
        assert registry.resolve("lint_clean") is not None
        assert registry.candidates() == ["commit_in_repo", "lint_clean"]


async def test_crash_unregisters_checkers() -> None:
    """插件崩溃 → 崩溃路径回调注销；死插件的 checker 不再可 resolve。"""
    spec = _checker_spec("boomy-plugin", ["commit_in_repo"])
    registry = CheckerRegistry()
    async with Context() as ctx:
        unit = _PluginUnit("boomy-plugin", boom=True)
        report, (ctx2, fibers, state, session, route_registry) = await _mount_with_sink(
            ctx, spec=spec, unit=unit, checker_factory=_make_checker, registry=registry
        )
        assert report.outcomes[0].status == "mounted"
        assert registry.resolve("commit_in_repo") is not None

        # 触发崩溃：经 bridge 命令调用（wrapper 捕获异常 → on_crash）
        from ghrah.subject.runtime.ouroboros_bridge import bridge_command

        result = await bridge_command(ctx, "boomy-plugin_run", {})
        assert result["success"] is False
        assert "crashed" in result["error"]
        # 崩溃注销：checker 消失
        assert registry.resolve("commit_in_repo") is None
        assert state.specs.get("boomy-plugin") is None


async def test_no_factory_checkers_not_registered() -> None:
    """声明 checker 但无工厂 → 不注册（候选缺失由内核 submit 记录）。"""
    spec = _checker_spec("spec-only-checkers", ["commit_in_repo"])
    registry = CheckerRegistry()
    async with Context() as ctx:
        report, _ = await _mount_with_sink(
            ctx,
            spec=spec,
            unit=_PluginUnit("spec-only-checkers"),
            checker_factory=None,
            registry=registry,
        )
        assert report.outcomes[0].status == "mounted"
        assert registry.resolve("commit_in_repo") is None


async def test_unit_not_present_sink_none_does_not_crash() -> None:
    """taskstore unit 不在场 → on_checkers=None，装配链照常完成（日志降级）。"""
    spec = _checker_spec("orphan-plugin", ["commit_in_repo"])
    async with Context() as ctx:
        report, _ = await _mount_with_sink(
            ctx,
            spec=spec,
            unit=_PluginUnit("orphan-plugin"),
            checker_factory=_make_checker,
            registry=None,
        )
        assert report.outcomes[0].status == "mounted"
