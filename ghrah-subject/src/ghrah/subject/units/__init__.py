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

    from ghrah.subject.units.manifest_store import ManifestStoreUnit
    from ghrah.subject.units.persistence import PersistenceUnit
    from ghrah.subject.units.sandbox import SandboxUnit

    for unit in (
        PersistenceUnit(engine.config),
        SandboxUnit(engine.config),
        ManifestStoreUnit(engine.config),
    ):
        engine.register_unit(unit)
