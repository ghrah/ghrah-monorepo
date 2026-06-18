# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Dependency sorting for Subject runtime units."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from typing import Any

from ghrah.subject.runtime.service_keys import CAPABILITY_REGISTRY, SubjectServiceKey
from ghrah.subject.unit.base import SubjectUnit

__all__ = ["topological_sort"]


def topological_sort(
    units: Mapping[str, SubjectUnit],
    runtime_services: set[SubjectServiceKey[Any]] | None = None,
) -> list[SubjectUnit]:
    """Return units sorted by service dependencies."""

    runtime_service_names = {
        key.name for key in (runtime_services or {CAPABILITY_REGISTRY})
    }
    provider_by_service: dict[str, str] = {}

    for unit_name, unit in units.items():
        for provided in unit.meta.provides:
            provider = provider_by_service.get(provided.name)
            if provider is not None:
                raise ValueError(
                    f"Subject service '{provided.name}' is provided by multiple units: "
                    f"{provider}, {unit_name}."
                )
            provider_by_service[provided.name] = unit_name

    edges: dict[str, list[str]] = defaultdict(list)
    indegree = {name: 0 for name in units}

    for unit_name, unit in units.items():
        for required in unit.meta.requires:
            if required.name in runtime_service_names:
                continue
            provider = provider_by_service.get(required.name)
            if provider is None:
                raise ValueError(
                    f"Required subject service '{required.name}' for unit "
                    f"'{unit_name}' has no provider."
                )
            if provider == unit_name:
                continue
            edges[provider].append(unit_name)
            indegree[unit_name] += 1

    ready = deque(name for name in units if indegree[name] == 0)
    ordered_names: list[str] = []

    while ready:
        current = ready.popleft()
        ordered_names.append(current)
        for dependent in edges[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if len(ordered_names) != len(units):
        cycle_nodes = [name for name in units if indegree[name] > 0]
        raise ValueError(
            "Dependency cycle detected among units: " + ", ".join(cycle_nodes)
        )

    return [units[name] for name in ordered_names]
