from __future__ import annotations

import logging
from typing import Any

import pytest

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import CAPABILITY_REGISTRY, SubjectServiceKey
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta, UnitState

SERVICE_A = SubjectServiceKey[object]("engine_service_a")


class _LifecycleUnit(SubjectUnit):
    def __init__(
        self,
        name: str,
        *,
        requires: frozenset[SubjectServiceKey[Any]] = frozenset(),
        provides: frozenset[SubjectServiceKey[Any]] = frozenset(),
        fail_init: bool = False,
        fail_start: bool = False,
    ) -> None:
        self._meta = UnitMeta(
            name=name,
            requires=requires,
            provides=provides,
            routes=RouteSpec(),
        )
        self.fail_init = fail_init
        self.fail_start = fail_start
        self.calls: list[str] = []

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def init(self, ctx: Any) -> None:
        self.calls.append("init")
        if self.fail_init:
            raise RuntimeError(f"{self.meta.name} init failed")

    async def start(self) -> None:
        self.calls.append("start")
        if self.fail_start:
            raise RuntimeError(f"{self.meta.name} start failed")

    async def stop(self) -> None:
        self.calls.append("stop")


class _EntryPoint:
    name = "plug"

    def load(self) -> Any:
        return lambda: _LifecycleUnit("plug")


class _EntryPoints:
    def select(self, *, group: str) -> list[_EntryPoint]:
        assert group == "ghrah.subject.units"
        return [_EntryPoint()]


async def test_engine_lifecycle_states_and_idempotent_stop() -> None:
    engine = SubjectEngine(SubjectConfig())
    unit = _LifecycleUnit("unit")
    engine.register_unit(unit)

    assert engine.get_state("unit") == UnitState.REGISTERED

    await engine.start()

    assert unit.calls == ["init", "start"]
    assert engine.get_state("unit") == UnitState.STARTED

    await engine.stop()
    await engine.stop()

    assert unit.calls == ["init", "start", "stop"]
    assert engine.get_state("unit") == UnitState.STOPPED


async def test_engine_init_failure_rolls_back_initialized_units() -> None:
    engine = SubjectEngine(SubjectConfig())
    first = _LifecycleUnit("first")
    second = _LifecycleUnit("second", fail_init=True)
    engine.register_unit(first)
    engine.register_unit(second)

    with pytest.raises(RuntimeError, match="second init failed"):
        await engine.start()

    assert first.calls == ["init", "stop"]
    assert second.calls == ["init"]
    assert engine.get_state("first") == UnitState.STOPPED
    assert engine.get_state("second") == UnitState.FAILED


async def test_engine_start_failure_rolls_back_initialized_units() -> None:
    engine = SubjectEngine(SubjectConfig())
    first = _LifecycleUnit("first")
    second = _LifecycleUnit("second", fail_start=True)
    engine.register_unit(first)
    engine.register_unit(second)

    with pytest.raises(RuntimeError, match="second start failed"):
        await engine.start()

    assert first.calls == ["init", "start", "stop"]
    assert second.calls == ["init", "start", "stop"]
    assert engine.get_state("first") == UnitState.STOPPED
    assert engine.get_state("second") == UnitState.FAILED


def test_engine_validate_uses_topological_dependencies_and_runtime_seed() -> None:
    engine = SubjectEngine(SubjectConfig())
    provider = _LifecycleUnit("provider", provides=frozenset({SERVICE_A}))
    consumer = _LifecycleUnit("consumer", requires=frozenset({SERVICE_A}))
    needs_seed = _LifecycleUnit("needs_seed", requires=frozenset({CAPABILITY_REGISTRY}))
    engine.register_unit(consumer)
    engine.register_unit(needs_seed)
    engine.register_unit(provider)

    ordered = engine.validate()

    assert [unit.meta.name for unit in ordered] == [
        "needs_seed",
        "provider",
        "consumer",
    ]


async def test_engine_seeds_capability_registry_service() -> None:
    engine = SubjectEngine(SubjectConfig())
    unit = _LifecycleUnit("unit", requires=frozenset({CAPABILITY_REGISTRY}))
    engine.register_unit(unit)

    await engine.start()

    assert engine.context.services.require(CAPABILITY_REGISTRY) is engine.capability_registry

    await engine.stop()


def test_discover_records_candidates_without_enabling(monkeypatch: Any) -> None:
    engine = SubjectEngine(SubjectConfig())
    monkeypatch.setattr("ghrah.subject.runtime.engine.entry_points", lambda: _EntryPoints())

    engine.discover()

    assert "plug" in engine.discovered
    assert engine.get_unit("plug") is None


def test_enable_from_config_uses_allowlist_and_warns_for_missing(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    engine = SubjectEngine(
        SubjectConfig(enabled_third_party_units=["plug", "missing"])
    )
    monkeypatch.setattr("ghrah.subject.runtime.engine.entry_points", lambda: _EntryPoints())
    engine.discover()

    with caplog.at_level(logging.WARNING):
        engine.enable_from_config()

    assert engine.get_unit("plug") is not None
    assert engine.get_state("plug") == UnitState.REGISTERED
    assert "missing" in caplog.text


def test_allowlist_empty_does_not_enable_discovered_units(monkeypatch: Any) -> None:
    engine = SubjectEngine(SubjectConfig())
    monkeypatch.setattr("ghrah.subject.runtime.engine.entry_points", lambda: _EntryPoints())
    engine.discover()

    engine.enable_from_config()

    assert engine.get_unit("plug") is None


def test_register_unit_rejects_duplicates() -> None:
    engine = SubjectEngine(SubjectConfig())
    engine.register_unit(_LifecycleUnit("unit"))

    with pytest.raises(ValueError, match="already registered"):
        engine.register_unit(_LifecycleUnit("unit"))
