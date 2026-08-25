# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Built-in Subject unit registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ouroboros import Context, Fiber  # type: ignore[import-untyped]

    from ghrah.subject.config import SubjectConfig
    from ghrah.subject.runtime.engine import SubjectEngine
    from ghrah.subject.unit.base import SubjectUnit

__all__ = ["mount_builtin_units", "register_builtin_units"]


async def mount_builtin_units(
    ctx: Context,
    config: SubjectConfig,
    *,
    profile: str = "coexistence",
) -> dict[str, Fiber]:
    """Mount migrated built-in units as Ouroboros plugins (阶段 2 增长中).

    与 ``register_builtin_units`` 对称；只挂已原生化（Ouroboros）的 unit，
    返回 ``{unit.meta.name: fiber}``。**逐个挂载并等 ACTIVE**（对齐旧
    engine 顺序 start 语义；实测并发挂载会让多个 store 同时打开同一
    SQLite 文件触发 ``database is locked``）。``full`` 分支**不含**
    cluster_transport（归 MVP 项① Core Unit；transport kind 校验随之归项①）。
    """

    if profile not in {"coexistence", "full"}:
        raise ValueError(f"Unknown built-in Subject unit profile: {profile}")

    from ghrah.subject.runtime.ouroboros_bridge import mount_unit, wait_active
    from ghrah.subject.units.ability_runner import AbilityRunnerUnit
    from ghrah.subject.units.hitl_notary import HITLNotaryUnit
    from ghrah.subject.units.hitl_policy import HITLPolicyUnit
    from ghrah.subject.units.ledger import LedgerUnit
    from ghrah.subject.units.manifest_store import ManifestStoreUnit
    from ghrah.subject.units.permissions import PermissionsUnit
    from ghrah.subject.units.persistence import PersistenceUnit
    from ghrah.subject.units.recovery import DesiredStateUnit
    from ghrah.subject.units.sandbox import SandboxUnit
    from ghrah.subject.units.task import TaskUnit
    from ghrah.subject.units.workspace import WorkspaceUnit

    units: list[SubjectUnit] = [
        PersistenceUnit(config),
        SandboxUnit(config),
        ManifestStoreUnit(config),
        LedgerUnit(config),
        WorkspaceUnit(config),
        HITLPolicyUnit(config),
        PermissionsUnit(config),
        HITLNotaryUnit(config),
        AbilityRunnerUnit(config),
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


def register_builtin_units(
    engine: SubjectEngine,
    *,
    profile: str = "coexistence",
) -> None:
    """Register built-in Subject units for the requested migration profile."""

    if profile not in {"coexistence", "full"}:
        raise ValueError(f"Unknown built-in Subject unit profile: {profile}")

    from ghrah.subject.units.ability_runner import AbilityRunnerUnit
    from ghrah.subject.units.cluster_transport import ClusterTransportUnit
    from ghrah.subject.units.hitl_notary import HITLNotaryUnit
    from ghrah.subject.units.hitl_policy import HITLPolicyUnit
    from ghrah.subject.units.ledger import LedgerUnit
    from ghrah.subject.units.manifest_store import ManifestStoreUnit
    from ghrah.subject.units.permissions import PermissionsUnit
    from ghrah.subject.units.persistence import PersistenceUnit
    from ghrah.subject.units.project import ProjectUnit
    from ghrah.subject.units.recovery import DesiredStateUnit, RecoveryUnit
    from ghrah.subject.units.sandbox import SandboxUnit
    from ghrah.subject.units.task import TaskUnit
    from ghrah.subject.units.websocket_observer_endpoint import (
        WebSocketObserverEndpointUnit,
    )
    from ghrah.subject.units.workspace import WorkspaceUnit

    units = [
        PersistenceUnit(engine.config),
        SandboxUnit(engine.config),
        ManifestStoreUnit(engine.config),
        LedgerUnit(engine.config),
        WorkspaceUnit(engine.config),
        HITLPolicyUnit(engine.config),
        PermissionsUnit(engine.config),
        HITLNotaryUnit(engine.config),
        AbilityRunnerUnit(engine.config),
        TaskUnit(engine.config),
        DesiredStateUnit(engine.config),
    ]

    if profile == "full":
        cfg = engine.config
        if cfg.transport.core != "websocket":
            raise ValueError(
                f"Unsupported core transport kind: {cfg.transport.core!r} "
                "(Stage 2 only implements 'websocket'; ipc/grpc reserved)."
            )
        if cfg.transport.observer != "websocket":
            raise ValueError(
                f"Unsupported observer transport kind: {cfg.transport.observer!r} "
                "(Stage 2 only implements 'websocket'; ipc/grpc/http reserved)."
            )
        units.extend(
            [
                WebSocketObserverEndpointUnit(engine.config),
                ClusterTransportUnit(engine.config),
                ProjectUnit(engine.config),
                RecoveryUnit(engine.config),
            ]
        )

    for unit in units:
        engine.register_unit(unit)
