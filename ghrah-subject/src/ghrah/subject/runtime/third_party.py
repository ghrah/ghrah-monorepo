# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""第三方 Subject Unit 发现与 allowlist 启用（Ouroboros 形态）。

保留旧 ``SubjectEngine.discover()/enable_from_config()`` 语义（定位文档
§原则9：subject 是高权限 effect host，第三方默认不启用——发现≠启用，
allowlist 显式列出才挂载），底层改为 ``ctx.plugin(mount_unit(unit))``
启动期挂载（运行时动态挂载能力归 registry/热插拔 API）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any

from ghrah.subject.runtime.ouroboros_bridge import mount_unit, wait_active
from ghrah.subject.unit.base import SubjectUnit

if TYPE_CHECKING:
    from ouroboros import Context, Fiber  # type: ignore[import-untyped]

    from ghrah.subject.config import SubjectConfig

__all__ = [
    "DiscoveredUnit",
    "discover",
    "mount_third_party_units",
    "resolve_discovered",
]

logger = logging.getLogger(__name__)

DiscoveredUnit = SubjectUnit | Callable[[], SubjectUnit]


def discover(group: str = "ghrah.subject.units") -> dict[str, DiscoveredUnit]:
    """发现第三方 unit 候选（entry_points），不启用、不实例化。"""

    discovered: dict[str, DiscoveredUnit] = {}
    try:
        eps: Any = entry_points()
        selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, ())
    except Exception:
        logger.exception("Failed to inspect Subject unit entry points.")
        return discovered

    for entry_point in selected:
        try:
            loaded = entry_point.load()
        except Exception:
            logger.exception(
                "Failed to load Subject unit entry point '%s'.",
                entry_point.name,
            )
            continue
        discovered[entry_point.name] = loaded
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
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber, timeout=10.0)
        fibers[unit.meta.name] = fiber
    return fibers
