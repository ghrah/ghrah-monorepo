from __future__ import annotations

import pytest

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.units._commands import (
    CHAIN_HISTORY_COMMANDS,
    MANIFEST_COMMANDS,
    PERSIST_COMMANDS,
    TASK_COMMANDS,
    WORKSPACE_COMMANDS,
)
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
    assert isinstance(engine.get_unit("ability_runner"), AbilityRunnerUnit)
    assert isinstance(engine.get_unit("task"), TaskUnit)
    assert isinstance(engine.get_unit("desired_state"), DesiredStateUnit)
    assert engine.get_unit("websocket_core_transport") is None
    assert engine.get_unit("websocket_observer_endpoint") is None
    assert engine.get_unit("forward") is None
    assert engine.get_unit("cluster_transport") is None
    assert engine.get_unit("project") is None
    assert engine.get_unit("recovery") is None


def test_register_builtin_units_full_registers_cluster_and_project_units() -> None:
    engine = SubjectEngine(SubjectConfig())

    engine.register_builtin_units(profile="full")

    cluster_transport = engine.get_unit("cluster_transport")
    assert isinstance(cluster_transport, ClusterTransportUnit)
    # D2：cluster_transport 不暴露任何命令路由（transport 层）
    assert cluster_transport.meta.routes.commands == frozenset()
    assert cluster_transport.meta.routes.long_running_commands == frozenset()
    assert isinstance(
        engine.get_unit("websocket_observer_endpoint"),
        WebSocketObserverEndpointUnit,
    )
    assert isinstance(engine.get_unit("project"), ProjectUnit)
    assert isinstance(engine.get_unit("recovery"), RecoveryUnit)
    assert isinstance(engine.get_unit("desired_state"), DesiredStateUnit)
    assert engine.get_unit("websocket_core_transport") is None
    assert engine.get_unit("forward") is None


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
    ability_runner = engine.get_unit("ability_runner")
    task = engine.get_unit("task")

    assert persistence is not None
    assert manifest_store is not None
    assert ledger is not None
    assert workspace is not None
    assert hitl_notary is not None
    assert ability_runner is not None
    assert task is not None
    assert persistence.meta.routes.commands == PERSIST_COMMANDS
    assert manifest_store.meta.routes.commands == MANIFEST_COMMANDS
    assert ledger.meta.routes.commands == CHAIN_HISTORY_COMMANDS
    assert workspace.meta.routes.commands == WORKSPACE_COMMANDS
    assert hitl_notary.meta.routes.commands == frozenset({"hitl_response"})
    assert task.meta.routes.commands == TASK_COMMANDS
    # D10：ability_runner 只声明 long_running_commands，commands 为空
    assert ability_runner.meta.routes.long_running_commands == frozenset({"execute_ability"})

    for unit in (persistence, manifest_store, ledger, workspace, hitl_notary, ability_runner, task):
        assert unit.meta.routes.commands.isdisjoint(unit.meta.routes.long_running_commands)
