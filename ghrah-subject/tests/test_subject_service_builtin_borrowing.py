from __future__ import annotations

from pathlib import Path

from ghrah.subject.config import SubjectConfig
from ghrah.subject.service import SubjectService
from ghrah.subject.units.hitl_notary import HITLNotaryUnit
from ghrah.subject.units.ledger import LedgerUnit
from ghrah.subject.units.manifest_store import ManifestStoreUnit
from ghrah.subject.units.permissions import PermissionsUnit
from ghrah.subject.units.persistence import PersistenceUnit
from ghrah.subject.units.sandbox import SandboxUnit
from ghrah.subject.units.workspace import WorkspaceUnit

CUSTOM_AUTO_ABILITY_YAML = """\
manifest: ability
version: "1"
metadata:
  namespace: custom
  name: auto_tool
  description: Auto-approved tool
  permissions:
    require_hitl: false
tool:
  name: auto_tool
  description: Auto-approved tool
  parameters: {}
implementation:
  type: builtin
  handler: custom_auto_tool
"""


async def test_subject_service_borrows_pr3a_pr3b_builtin_unit_instances(
    tmp_path: Path,
) -> None:
    config = SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )
    service = SubjectService(config)

    await service._init_subsystems()
    try:
        persistence = service._engine.get_unit("persistence")
        sandbox = service._engine.get_unit("sandbox")
        manifest_store = service._engine.get_unit("manifest_store")
        ledger = service._engine.get_unit("ledger")
        workspace = service._engine.get_unit("workspace")
        permissions = service._engine.get_unit("permissions")
        hitl_notary = service._engine.get_unit("hitl_notary")

        assert isinstance(persistence, PersistenceUnit)
        assert isinstance(sandbox, SandboxUnit)
        assert isinstance(manifest_store, ManifestStoreUnit)
        assert isinstance(ledger, LedgerUnit)
        assert isinstance(workspace, WorkspaceUnit)
        assert isinstance(permissions, PermissionsUnit)
        assert isinstance(hitl_notary, HITLNotaryUnit)
        assert service._persistence is persistence.service
        assert service._sandbox is sandbox.service
        assert service._manifest_store is manifest_store.service
        assert service._ledger is ledger.service
        assert service._workspace_mgr is workspace.manager
        assert service._permission_checker is permissions.service
        assert service._hitl_notary is hitl_notary.service
        assert service._workspace_mgr is not None
        assert service._workspace_mgr.sandbox is sandbox.service
    finally:
        await service.stop()


async def test_subject_service_manifest_crud_updates_hitl_policy_without_restart(
    tmp_path: Path,
) -> None:
    config = SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )
    service = SubjectService(config)

    await service._init_subsystems()
    try:
        assert service._hitl_notary is not None
        before = service._hitl_notary.check_request("agent-a", "custom_auto_tool")
        assert before.approved is False

        result = await service._handle_manifest_command(
            "manifest_put_ability",
            {
                "full_name": "custom.auto_tool",
                "content": CUSTOM_AUTO_ABILITY_YAML,
            },
        )

        after = service._hitl_notary.check_request("agent-a", "custom_auto_tool")
        assert result["success"] is True
        assert after.approved is True
        assert after.reason == "manifest_auto_approved"
    finally:
        await service.stop()
