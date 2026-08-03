# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Built-in Subject unit registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ghrah.subject.runtime.engine import SubjectEngine

__all__ = ["register_builtin_units"]


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
        units.extend([
            WebSocketObserverEndpointUnit(engine.config),
            ClusterTransportUnit(engine.config),
            ProjectUnit(engine.config),
            RecoveryUnit(engine.config),
        ])

    for unit in units:
        engine.register_unit(unit)
