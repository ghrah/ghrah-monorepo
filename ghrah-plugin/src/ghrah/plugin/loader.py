# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件发现（entry_point 导入式，D1；发现 ≠ 启用）。

组名 ``ghrah.plugins``；entry point 值指向模块属性（如 ``pkg.spec:spec``），
目标为 ``PluginSpec`` 实例或零参 callable 返回实例。
plugin.yaml 零导入形态登记到 PM 战役（上游 §13.8）再议。

发现失败不 raise：加载/校验失败转 ``LoadIssue`` 供 verify 汇总（A18）。
A8 底座下沉（third_party.py 复用本模块）归 S2 接线期，S0 两处同范式零交互。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

from ghrah.plugin.spec import PluginSpec, migrate_spec

__all__ = ["DiscoveredPlugin", "LoadIssue", "discover_plugins"]

logger = logging.getLogger(__name__)

PLUGIN_ENTRY_POINT_GROUP = "ghrah.plugins"


@dataclass(frozen=True)
class DiscoveredPlugin:
    """发现成功的插件（已解析为合法 PluginSpec）。

    Attributes:
        spec: 插件声明式契约。
        entry_point_name: entry point 名称。
        dist_name: 来源发行版名（未知为 None）。
    """

    spec: PluginSpec
    entry_point_name: str
    dist_name: str | None = None


@dataclass(frozen=True)
class LoadIssue:
    """发现失败的插件条目（加载/校验/身份异常，不中断整体发现）。

    Attributes:
        entry_point: entry point 名称（或描述）。
        error: 人读错误摘要。
    """

    entry_point: str
    error: str


def _resolve_spec_target(loaded: Any) -> PluginSpec:
    """把 entry point 加载结果归一为 PluginSpec（实例或零参 callable）。"""

    target = loaded() if callable(loaded) and not isinstance(loaded, PluginSpec) else loaded
    if isinstance(target, PluginSpec):
        return target
    raise TypeError(f"entry point target is not a PluginSpec: {type(target).__name__}")


def discover_plugins(
    group: str = PLUGIN_ENTRY_POINT_GROUP,
) -> tuple[list[DiscoveredPlugin], list[LoadIssue]]:
    """经 entry_points 发现插件候选，不启用、不挂载。

    Returns:
        (发现成功列表, 发现失败列表)；两者均按 entry_points 迭代序。
        同一 plugin_id 跨 entry point 重复出现 → 后到者转 LoadIssue（身份撞名）。
    """

    discovered: list[DiscoveredPlugin] = []
    issues: list[LoadIssue] = []
    seen_ids: dict[str, str] = {}
    try:
        eps: Any = entry_points()
        selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, ())
    except Exception:
        logger.exception("Failed to inspect plugin entry points.")
        return discovered, issues

    for entry_point in selected:
        dist_name = getattr(entry_point, "dist", None)
        dist_name = getattr(dist_name, "name", None) if dist_name is not None else None
        try:
            loaded = entry_point.load()
            spec = _resolve_spec_target(loaded)
            raw = spec.model_dump()
            migrated = migrate_spec(raw)
            if migrated is not raw and migrated != raw:
                spec = PluginSpec.model_validate(migrated)
        except Exception as exc:
            issues.append(LoadIssue(entry_point=entry_point.name, error=str(exc)))
            continue
        owner = seen_ids.get(spec.plugin_id)
        if owner is not None:
            issues.append(
                LoadIssue(
                    entry_point=entry_point.name,
                    error=f"duplicate plugin_id {spec.plugin_id!r} "
                    f"(already discovered via {owner!r})",
                )
            )
            continue
        seen_ids[spec.plugin_id] = entry_point.name
        discovered.append(
            DiscoveredPlugin(spec=spec, entry_point_name=entry_point.name, dist_name=dist_name)
        )
    return discovered, issues
