# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件发现（entry_point 导入式；发现 ≠ 启用）。

组名 ``ghrah.plugins``；entry point 值指向模块属性（如 ``pkg.spec:spec``），
目标为 ``PluginSpec`` 实例、零参 callable 返回实例，或暴露 spec 的模块/对象
（属性名 ``plugin_spec`` / ``spec``）。plugin.yaml 零导入形态留待后续再议。

发现失败不 raise：加载/校验失败转 ``LoadIssue`` 供 verify 汇总。
``third_party.py`` 的第三方 unit 发现复用本模块 ``iter_entry_point_values``
底座（两组发现通道同范式，但返回类型各自适配）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

from ghrah.plugin.spec import PluginSpec, migrate_spec

__all__ = [
    "DiscoveredPlugin",
    "LoadIssue",
    "LoadedEntry",
    "discover_plugins",
    "iter_entry_point_values",
]

logger = logging.getLogger(__name__)

PLUGIN_ENTRY_POINT_GROUP = "ghrah.plugins"


@dataclass(frozen=True)
class DiscoveredPlugin:
    """发现成功的插件（已解析为合法 PluginSpec）。

    Attributes:
        spec: 插件声明式契约。
        entry_point_name: entry point 名称。
        dist_name: 来源发行版名（未知为 None）。
        unit_factory: 可选宿主侧 unit 工厂（发现期 duck-typing 探测结果；
            None = spec-only，可协商不可挂载）。探测归宿主装配链。
        checker_factory: 可选 checker 工厂（发现期 duck-typing 探测结果；
            签名 ``(name: str) -> Checker``，None = 不供 checker）。
    """

    spec: PluginSpec
    entry_point_name: str
    dist_name: str | None = None
    unit_factory: Callable[[], Any] | None = None
    checker_factory: Callable[[str], Any] | None = None


@dataclass(frozen=True)
class LoadIssue:
    """发现失败的插件条目（加载/校验/身份异常，不中断整体发现）。

    Attributes:
        entry_point: entry point 名称（或描述）。
        error: 人读错误摘要。
    """

    entry_point: str
    error: str


@dataclass(frozen=True)
class LoadedEntry:
    """entry point 加载底座的单条成功记录。

    Attributes:
        name: entry point 名称。
        value: 加载结果（未做任何类型归一，由消费方适配）。
        dist_name: 来源发行版名（未知为 None）。
    """

    name: str
    value: Any
    dist_name: str | None = None


def iter_entry_point_values(group: str) -> tuple[list[LoadedEntry], list[LoadIssue]]:
    """共享 entry_points 迭代/加载底座。

    两组发现通道（``ghrah.plugins`` / ``ghrah.subject.units``）共用：
    迭代 → load → 异常转 ``LoadIssue``（不中断整体发现）。返回值的
    类型归一（PluginSpec / SubjectUnit 工厂）由各消费方适配。
    """

    loaded: list[LoadedEntry] = []
    issues: list[LoadIssue] = []
    try:
        eps: Any = entry_points()
        selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, ())
    except Exception:
        logger.exception("Failed to inspect entry points (group=%s).", group)
        return loaded, issues

    for entry_point in selected:
        dist_name = getattr(entry_point, "dist", None)
        dist_name = getattr(dist_name, "name", None) if dist_name is not None else None
        try:
            value = entry_point.load()
        except Exception as exc:
            issues.append(LoadIssue(entry_point=entry_point.name, error=str(exc)))
            continue
        loaded.append(LoadedEntry(name=entry_point.name, value=value, dist_name=dist_name))
    return loaded, issues


_SPEC_ATTRS = ("plugin_spec", "PLUGIN_SPEC", "spec")


def _resolve_spec_target(loaded: Any) -> PluginSpec:
    """把 entry point 加载结果归一为 PluginSpec。

    支持三种形态（优先级降序）：
    1. ``PluginSpec`` 实例；
    2. 零参 callable 返回 ``PluginSpec``；
    3. 模块/命名空间对象，其 ``plugin_spec`` / ``PLUGIN_SPEC`` / ``spec``
       属性为 ``PluginSpec`` 实例或返回实例的零参 callable。
    """

    if isinstance(loaded, PluginSpec):
        return loaded
    if callable(loaded) and not isinstance(loaded, type):
        produced = loaded()
        if isinstance(produced, PluginSpec):
            return produced
    for attr in _SPEC_ATTRS:
        candidate = getattr(loaded, attr, None)
        if candidate is None:
            continue
        if callable(candidate) and not isinstance(candidate, PluginSpec):
            candidate = candidate()
        if isinstance(candidate, PluginSpec):
            return candidate
    raise TypeError(f"entry point target is not a PluginSpec: {type(loaded).__name__}")


def _detect_unit_factory(spec: PluginSpec, loaded: Any) -> Callable[[], Any] | None:
    """unit 工厂 duck-typing 探测（发现期，零参 callable → 宿主 SubjectUnit）。

    约定（优先级降序）：
    1. ``PluginSpec`` 子类以类属性/字段声明 ``unit_factory``；
    2. ``PluginSpec`` 子类声明 ``create_unit``；
    3. entry point 加载结果（模块/对象）暴露 ``unit_factory``；
    4. entry point 加载结果（模块/对象）暴露 ``create_unit``。

    注意：普通 ``PluginSpec``（``extra="forbid"``）无法在实例上挂属性，
    故需宿主 unit 的插件应使用子类声明或模块形态。探测不到 → None
    （spec-only：可协商不可挂载）。
    """

    for candidate in (
        getattr(spec, "unit_factory", None),
        getattr(spec, "create_unit", None),
        getattr(loaded, "unit_factory", None),
        getattr(loaded, "create_unit", None),
    ):
        if callable(candidate):
            return candidate
    return None


def _detect_checker_factory(spec: PluginSpec, loaded: Any) -> Callable[[str], Any] | None:
    """checker 工厂 duck-typing 探测（发现期，签名 ``(name: str) -> Checker``）。

    约定（优先级降序，同 unit 工厂范式）：
    1. ``PluginSpec`` 子类以类属性/字段声明 ``checker_factory``；
    2. entry point 加载结果（模块/对象）暴露 ``checker_factory``；
    3. entry point 加载结果（模块/对象）暴露 ``create_checker``。

    探测不到 → None（该插件不供 checker；spec 声明的 ``provides.checkers``
    由装配链记为候选缺失）。
    """

    for candidate in (
        getattr(spec, "checker_factory", None),
        getattr(loaded, "checker_factory", None),
        getattr(loaded, "create_checker", None),
    ):
        if callable(candidate):
            return candidate
    return None


def discover_plugins(
    group: str = PLUGIN_ENTRY_POINT_GROUP,
) -> tuple[list[DiscoveredPlugin], list[LoadIssue]]:
    """经 entry_points 发现插件候选，不启用、不挂载。

    Returns:
        (发现成功列表, 发现失败列表)；两者均按 entry_points 迭代序。
        同一 plugin_id 跨 entry point 重复出现 → 后到者转 LoadIssue（身份撞名）。
        ``DiscoveredPlugin.unit_factory`` 为发现期 duck-typing 探测结果
        （None = spec-only，可协商不可挂载）。
    """

    discovered: list[DiscoveredPlugin] = []
    seen_ids: dict[str, str] = {}
    loaded, issues = iter_entry_point_values(group)

    for entry in loaded:
        try:
            spec = _resolve_spec_target(entry.value)
            raw = spec.model_dump()
            migrated = migrate_spec(raw)
            if migrated is not raw and migrated != raw:
                spec = PluginSpec.model_validate(migrated)
        except Exception as exc:
            issues.append(LoadIssue(entry_point=entry.name, error=str(exc)))
            continue
        owner = seen_ids.get(spec.plugin_id)
        if owner is not None:
            issues.append(
                LoadIssue(
                    entry_point=entry.name,
                    error=f"duplicate plugin_id {spec.plugin_id!r} "
                    f"(already discovered via {owner!r})",
                )
            )
            continue
        seen_ids[spec.plugin_id] = entry.name
        discovered.append(
            DiscoveredPlugin(
                spec=spec,
                entry_point_name=entry.name,
                dist_name=entry.dist_name,
                unit_factory=_detect_unit_factory(spec, entry.value),
                checker_factory=_detect_checker_factory(spec, entry.value),
            )
        )
    return discovered, issues
