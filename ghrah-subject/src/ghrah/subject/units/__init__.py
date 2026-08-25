# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Built-in Subject unit registration (Ouroboros 形态)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ouroboros import Context, Fiber  # type: ignore[import-untyped]

    from ghrah.subject.config import SubjectConfig
    from ghrah.subject.unit.base import SubjectUnit

__all__ = ["mount_builtin_units"]


async def mount_builtin_units(
    ctx: Context,
    config: SubjectConfig,
    *,
    profile: str = "coexistence",
) -> dict[str, Fiber]:
    """Mount built-in units as Ouroboros plugins.

    聚合裁决后收敛：coexistence = 6（sandbox/manifest_store/ledger/workspace/
    task/desired_state——读写侧均不依赖已剔除的四件套）；full = 6 +
    observer/core_cluster_registry/project/recovery = 10。**逐个挂载并等
    ACTIVE**（对齐旧 engine 顺序 start 语义；实测并发挂载会让多个 store
    同时打开同一 SQLite 文件触发 ``database is locked``）。
    """

    if profile not in {"coexistence", "full"}:
        raise ValueError(f"Unknown built-in Subject unit profile: {profile}")

    from ghrah.subject.runtime.ouroboros_bridge import mount_unit, wait_active
    from ghrah.subject.units.ledger import LedgerUnit
    from ghrah.subject.units.manifest_store import ManifestStoreUnit
    from ghrah.subject.units.recovery import DesiredStateUnit
    from ghrah.subject.units.sandbox import SandboxUnit
    from ghrah.subject.units.task import TaskUnit
    from ghrah.subject.units.workspace import WorkspaceUnit

    units: list[SubjectUnit] = [
        SandboxUnit(config),
        ManifestStoreUnit(config),
        LedgerUnit(config),
        WorkspaceUnit(config),
        TaskUnit(config),
        DesiredStateUnit(config),
    ]

    if profile == "full":
        from ghrah.subject.units.core_cluster import CoreClusterRegistryUnit
        from ghrah.subject.units.project import ProjectUnit
        from ghrah.subject.units.recovery import RecoveryUnit
        from ghrah.subject.units.websocket_observer_endpoint import (
            WebSocketObserverEndpointUnit,
        )

        units.extend(
            [
                WebSocketObserverEndpointUnit(config),
                CoreClusterRegistryUnit(config),
                ProjectUnit(config),
                RecoveryUnit(config),
            ]
        )

    fibers: dict[str, Fiber] = {}
    for unit in units:
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber, timeout=10.0)
        fibers[unit.meta.name] = fiber
    return fibers
