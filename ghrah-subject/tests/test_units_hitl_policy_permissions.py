from __future__ import annotations

from pathlib import Path

from ghrah.subject.config import SubjectConfig
from ghrah.subject.permission_checker import PermissionDecision
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units.manifest_store import ManifestStoreUnit
from ghrah.subject.units.permissions import PermissionsUnit

CUSTOM_SHELL_ABILITY_YAML = """\
manifest: ability
version: "1"
metadata:
  namespace: custom
  name: guarded_shell
  description: Guarded shell tool
  permissions:
    require_hitl: false
    shell_access: true
    denied_commands:
      - rm
tool:
  name: guarded_shell
  description: Guarded shell tool
  parameters:
    command:
      type: string
      description: Command to run
      required: true
implementation:
  type: builtin
  handler: custom_guarded_shell
"""


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_hitl_policy_and_permissions_units_read_manifest_index_dynamically(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        manifest_store = engine.get_unit("manifest_store")
        permissions = engine.get_unit("permissions")
        hitl_notary = engine.get_unit("hitl_notary")
        assert isinstance(manifest_store, ManifestStoreUnit)
        assert isinstance(permissions, PermissionsUnit)
        assert hitl_notary is not None

        before_hitl = hitl_notary.service.check_request(
            "agent-a",
            "custom_guarded_shell",
        )
        before_permission = permissions.service.check_ability(
            "custom_guarded_shell",
            {"command": "rm -rf tmp"},
        )
        assert before_hitl.approved is False
        assert before_permission.decision == PermissionDecision.ALLOW

        put_result = await manifest_store.handle_command(
            "manifest_put_ability",
            {
                "full_name": "custom.guarded_shell",
                "content": CUSTOM_SHELL_ABILITY_YAML,
            },
            CommandContext.observer("req-1", session_id=None),
        )
        assert put_result["success"] is True

        after_hitl = hitl_notary.service.check_request(
            "agent-a",
            "custom_guarded_shell",
        )
        after_permission = permissions.service.check_ability(
            "custom_guarded_shell",
            {"command": "rm -rf tmp"},
        )

        assert after_hitl.approved is True
        assert after_hitl.reason == "manifest_auto_approved"
        assert after_permission.decision == PermissionDecision.DENY
        assert after_permission.reason == "Command denied by manifest: rm"
    finally:
        await engine.stop()
