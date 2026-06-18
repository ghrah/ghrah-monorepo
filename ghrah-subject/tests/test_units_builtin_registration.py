from __future__ import annotations

import pytest

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.units._commands import (
    CHAIN_HISTORY_COMMANDS,
    MANIFEST_COMMANDS,
    PERSIST_COMMANDS,
    WORKSPACE_COMMANDS,
)
from ghrah.subject.units.hitl_notary import HITLNotaryUnit
from ghrah.subject.units.hitl_policy import HITLPolicyUnit
from ghrah.subject.units.ledger import LedgerUnit
from ghrah.subject.units.manifest_store import ManifestStoreUnit
from ghrah.subject.units.permissions import PermissionsUnit
from ghrah.subject.units.persistence import PersistenceUnit
from ghrah.subject.units.sandbox import SandboxUnit
from ghrah.subject.units.workspace import WorkspaceUnit


def test_register_builtin_units_coexistence_registers_pr3a_pr3b_units() -> None:
    engine = SubjectEngine(SubjectConfig())

    engine.register_builtin_units(profile="coexistence")

    assert isinstance(engine.get_unit("persistence"), PersistenceUnit)
    assert isinstance(engine.get_unit("sandbox"), SandboxUnit)
    assert isinstance(engine.get_unit("manifest_store"), ManifestStoreUnit)
    assert isinstance(engine.get_unit("ledger"), LedgerUnit)
    assert isinstance(engine.get_unit("workspace"), WorkspaceUnit)
    assert isinstance(engine.get_unit("hitl_policy"), HITLPolicyUnit)
    assert isinstance(engine.get_unit("permissions"), PermissionsUnit)
    assert isinstance(engine.get_unit("hitl_notary"), HITLNotaryUnit)
    assert engine.get_unit("websocket_core_transport") is None


def test_register_builtin_units_rejects_unknown_profile() -> None:
    engine = SubjectEngine(SubjectConfig())

    with pytest.raises(ValueError, match="Unknown"):
        engine.register_builtin_units(profile="mystery")


def test_builtin_routes_use_protocol_command_sets_without_overlap() -> None:
    engine = SubjectEngine(SubjectConfig())
    engine.register_builtin_units(profile="coexistence")

    persistence = engine.get_unit("persistence")
    manifest_store = engine.get_unit("manifest_store")
    ledger = engine.get_unit("ledger")
    workspace = engine.get_unit("workspace")
    hitl_notary = engine.get_unit("hitl_notary")

    assert persistence is not None
    assert manifest_store is not None
    assert ledger is not None
    assert workspace is not None
    assert hitl_notary is not None
    assert persistence.meta.routes.commands == PERSIST_COMMANDS
    assert manifest_store.meta.routes.commands == MANIFEST_COMMANDS
    assert ledger.meta.routes.commands == CHAIN_HISTORY_COMMANDS
    assert workspace.meta.routes.commands == WORKSPACE_COMMANDS
    assert hitl_notary.meta.routes.commands == frozenset({"hitl_response"})

    for unit in (persistence, manifest_store, ledger, workspace, hitl_notary):
        assert unit.meta.routes.commands.isdisjoint(unit.meta.routes.long_running_commands)
