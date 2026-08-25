from __future__ import annotations

from pathlib import Path

from ouroboros import Context  # type: ignore[import-untyped]

from ghrah.subject.config import SubjectConfig
from ghrah.subject.permission_checker import PermissionDecision
from ghrah.subject.runtime.ouroboros_bridge import bridge_command
from ghrah.subject.units import mount_builtin_units

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

    async with Context() as ctx:
        await mount_builtin_units(ctx, config, profile="coexistence")

        hitl_notary = ctx.get("hitl_notary")
        permissions = ctx.get("permission_service")
        assert hitl_notary is not None
        assert permissions is not None

        before_hitl = hitl_notary.check_request(
            "agent-a",
            "custom_guarded_shell",
        )
        before_permission = permissions.check_ability(
            "custom_guarded_shell",
            {"command": "rm -rf tmp"},
        )
        assert before_hitl.approved is False
        assert before_permission.decision == PermissionDecision.ALLOW

        put_result = await bridge_command(
            ctx,
            "manifest_put_ability",
            {
                "full_name": "custom.guarded_shell",
                "content": CUSTOM_SHELL_ABILITY_YAML,
            },
        )
        assert put_result["success"] is True

        after_hitl = hitl_notary.check_request(
            "agent-a",
            "custom_guarded_shell",
        )
        after_permission = permissions.check_ability(
            "custom_guarded_shell",
            {"command": "rm -rf tmp"},
        )

        assert after_hitl.approved is True
        assert after_hitl.reason == "manifest_auto_approved"
        assert after_permission.decision == PermissionDecision.DENY
        assert after_permission.reason == "Command denied by manifest: rm"
