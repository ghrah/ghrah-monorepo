from __future__ import annotations

from typing import Any

import pytest

from ghrah.subject.runtime.dependency import topological_sort
from ghrah.subject.runtime.service_keys import CAPABILITY_REGISTRY, SubjectServiceKey
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta

SERVICE_A = SubjectServiceKey[object]("service_a")
SERVICE_B = SubjectServiceKey[object]("service_b")
SERVICE_C = SubjectServiceKey[object]("service_c")


class _Unit(SubjectUnit):
    def __init__(
        self,
        name: str,
        *,
        requires: frozenset[SubjectServiceKey[Any]] = frozenset(),
        provides: frozenset[SubjectServiceKey[Any]] = frozenset(),
    ) -> None:
        self._meta = UnitMeta(
            name=name,
            requires=requires,
            provides=provides,
            routes=RouteSpec(),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta


def test_topological_sort_orders_providers_before_consumers() -> None:
    provider = _Unit("provider", provides=frozenset({SERVICE_A}))
    consumer = _Unit("consumer", requires=frozenset({SERVICE_A}))
    independent = _Unit("independent")

    ordered = topological_sort(
        {
            "consumer": consumer,
            "independent": independent,
            "provider": provider,
        }
    )

    assert [unit.meta.name for unit in ordered] == [
        "independent",
        "provider",
        "consumer",
    ]


def test_runtime_services_do_not_need_unit_provider() -> None:
    unit = _Unit("needs_capability", requires=frozenset({CAPABILITY_REGISTRY}))

    ordered = topological_sort({"needs_capability": unit})

    assert ordered == [unit]


def test_missing_required_service_raises() -> None:
    unit = _Unit("consumer", requires=frozenset({SERVICE_A}))

    with pytest.raises(ValueError, match="has no provider"):
        topological_sort({"consumer": unit})


def test_multiple_providers_for_same_service_raise() -> None:
    first = _Unit("first", provides=frozenset({SERVICE_A}))
    second = _Unit("second", provides=frozenset({SERVICE_A}))

    with pytest.raises(ValueError, match="provided by multiple units"):
        topological_sort({"first": first, "second": second})


def test_dependency_cycle_raises_with_cycle_nodes() -> None:
    first = _Unit(
        "first",
        requires=frozenset({SERVICE_B}),
        provides=frozenset({SERVICE_A}),
    )
    second = _Unit(
        "second",
        requires=frozenset({SERVICE_A}),
        provides=frozenset({SERVICE_B}),
    )

    with pytest.raises(ValueError, match="first"):
        topological_sort({"first": first, "second": second})
