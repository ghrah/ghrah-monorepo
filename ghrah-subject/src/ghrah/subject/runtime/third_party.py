# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""第三方 Subject Unit 发现与 allowlist 启用（Ouroboros 形态）。

保留旧 discover()/enable_from_config() 语义（subject 是高权限 effect host，
第三方默认不启用——发现≠启用，allowlist 显式列出才挂载），底层改为
``ctx.plugin(mount_unit(unit))`` 启动期挂载（运行时动态挂载能力归
registry/热插拔 API）。

entry_points 迭代/加载底座下沉至 ``ghrah.plugin.loader.iter_entry_point_values``
（两组发现通道共用：``ghrah.plugins`` 插件 spec / ``ghrah.subject.units``
SubjectUnit 工厂）；本模块只保留 unit 领域适配。allowlist
（``enabled_third_party_units``）与插件信任闸（``plugin_trust``）分属
Subject 信任层两列配置，各司其职。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ghrah.plugin.loader import iter_entry_point_values

from ghrah.subject.runtime.ouroboros_bridge import mount_unit, wait_active
from ghrah.subject.unit.base import SubjectUnit

if TYPE_CHECKING:
    from ouroboros import Context, Fiber  # type: ignore[import-untyped]

    from ghrah.subject.config import SubjectConfig
    from ghrah.subject.runtime.route_registry import UnitRouteRegistry

__all__ = [
    "DiscoveredUnit",
    "discover",
    "mount_third_party_units",
    "resolve_discovered",
]

logger = logging.getLogger(__name__)

THIRD_PARTY_UNIT_GROUP = "ghrah.subject.units"

DiscoveredUnit = SubjectUnit | Callable[[], SubjectUnit]


def discover(group: str = THIRD_PARTY_UNIT_GROUP) -> dict[str, DiscoveredUnit]:
    """发现第三方 unit 候选（entry_points），不启用、不实例化。"""

    discovered: dict[str, DiscoveredUnit] = {}
    loaded, issues = iter_entry_point_values(group)
    for issue in issues:
        logger.warning(
            "Failed to load Subject unit entry point '%s': %s",
            issue.entry_point,
            issue.error,
        )
    for entry in loaded:
        discovered[entry.name] = entry.value
    return discovered


def resolve_discovered(unit_name: str, discovered: DiscoveredUnit) -> SubjectUnit:
    """实例化发现项并校验为 SubjectUnit（对齐旧 engine 语义）。"""

    unit = discovered if isinstance(discovered, SubjectUnit) else discovered()
    if not isinstance(unit, SubjectUnit):
        raise TypeError(f"Discovered Subject unit '{unit_name}' did not produce a SubjectUnit.")
    return unit


async def mount_third_party_units(
    ctx: Context,
    config: SubjectConfig,
    *,
    discovered: dict[str, DiscoveredUnit] | None = None,
    route_registry: UnitRouteRegistry | None = None,
) -> dict[str, Fiber]:
    """按 config allowlist 挂载第三方 unit（逐个挂载并等 ACTIVE）。"""

    candidates = discover() if discovered is None else discovered
    fibers: dict[str, Fiber] = {}
    for unit_name in config.enabled_third_party_units:
        entry = candidates.get(unit_name)
        if entry is None:
            logger.warning(
                "Subject unit '%s' is enabled in config but was not discovered.",
                unit_name,
            )
            continue
        unit = resolve_discovered(unit_name, entry)
        fiber = ctx.plugin(mount_unit(unit, route_registry=route_registry))
        await wait_active(fiber, timeout=10.0)
        fibers[unit.meta.name] = fiber
    return fibers
