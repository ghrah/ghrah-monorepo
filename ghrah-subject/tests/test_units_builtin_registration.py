from __future__ import annotations

import pytest

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.units._commands import MANIFEST_COMMANDS, PERSIST_COMMANDS
from ghrah.subject.units.manifest_store import ManifestStoreUnit
from ghrah.subject.units.persistence import PersistenceUnit
from ghrah.subject.units.sandbox import SandboxUnit


def test_register_builtin_units_coexistence_registers_pr3a_units() -> None:
    engine = SubjectEngine(SubjectConfig())

    engine.register_builtin_units(profile="coexistence")

    assert isinstance(engine.get_unit("persistence"), PersistenceUnit)
    assert isinstance(engine.get_unit("sandbox"), SandboxUnit)
    assert isinstance(engine.get_unit("manifest_store"), ManifestStoreUnit)
    assert engine.get_unit("websocket_core_transport") is None


def test_register_builtin_units_rejects_unknown_profile() -> None:
    engine = SubjectEngine(SubjectConfig())

    with pytest.raises(ValueError, match="Unknown"):
        engine.register_builtin_units(profile="mystery")


def test_pr3a_builtin_routes_use_protocol_command_sets() -> None:
    engine = SubjectEngine(SubjectConfig())
    engine.register_builtin_units(profile="coexistence")

    persistence = engine.get_unit("persistence")
    manifest_store = engine.get_unit("manifest_store")

    assert persistence is not None
    assert manifest_store is not None
    assert persistence.meta.routes.commands == PERSIST_COMMANDS
    assert manifest_store.meta.routes.commands == MANIFEST_COMMANDS
    assert persistence.meta.routes.commands.isdisjoint(
        persistence.meta.routes.long_running_commands
    )
    assert manifest_store.meta.routes.commands.isdisjoint(
        manifest_store.meta.routes.long_running_commands
    )
