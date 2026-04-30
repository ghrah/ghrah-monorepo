from __future__ import annotations

import os

from ghrah.manifest.types import PermissionFlags

from ghrah.subject.hitl.policy import HITLPolicy


def _make_permissions(**overrides: bool) -> PermissionFlags:
    return PermissionFlags(**overrides)


class TestHITLPolicyAutoApprove:
    def test_auto_approve_ability(self) -> None:
        policy = HITLPolicy(auto_approve_abilities=["read_file", "list_dir"])
        verdict = policy.check_ability("read_file")
        assert verdict.approved is True
        assert verdict.reason == "auto_approved"

    def test_auto_approve_overrides_manifest_require_hitl(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        policy = HITLPolicy(
            auto_approve_abilities=["write_file"],
            manifest_permissions=manifest_perms,
        )
        verdict = policy.check_ability("write_file")
        assert verdict.approved is True
        assert verdict.reason == "auto_approved"


class TestHITLPolicyManifestPermissions:
    def test_manifest_require_hitl_false_auto_approved(self) -> None:
        manifest_perms = {
            "conversation": PermissionFlags(),
        }
        policy = HITLPolicy(
            manifest_permissions=manifest_perms,
            require_approval_by_default=True,
        )
        verdict = policy.check_ability("conversation")
        assert verdict.approved is True
        assert verdict.reason == "manifest_auto_approved"

    def test_manifest_end_task_auto_approved(self) -> None:
        manifest_perms = {
            "end_task": PermissionFlags(),
        }
        policy = HITLPolicy(
            manifest_permissions=manifest_perms,
            require_approval_by_default=True,
        )
        verdict = policy.check_ability("end_task")
        assert verdict.approved is True
        assert verdict.reason == "manifest_auto_approved"

    def test_manifest_read_file_auto_approved(self) -> None:
        manifest_perms = {
            "read_file": PermissionFlags(fs_read_only=True),
        }
        policy = HITLPolicy(
            manifest_permissions=manifest_perms,
            require_approval_by_default=True,
        )
        verdict = policy.check_ability("read_file")
        assert verdict.approved is True
        assert verdict.reason == "manifest_auto_approved"

    def test_manifest_write_file_needs_hitl(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        policy = HITLPolicy(
            manifest_permissions=manifest_perms,
            require_approval_by_default=True,
        )
        verdict = policy.check_ability("write_file")
        assert verdict.approved is False
        assert verdict.reason == "requires_hitl_approval"

    def test_manifest_write_file_with_path_allowed(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        policy = HITLPolicy(
            manifest_permissions=manifest_perms,
            allowed_paths=["/tmp/data"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/tmp/data/output.txt"}
        )
        assert verdict.approved is True
        assert verdict.reason == "path_in_allowed_scope"

    def test_manifest_write_file_with_path_not_allowed(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        policy = HITLPolicy(
            manifest_permissions=manifest_perms,
            allowed_paths=["/tmp/data"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/etc/passwd"}
        )
        assert verdict.approved is False
        assert verdict.reason == "path_requires_hitl_approval"


class TestHITLPolicyFallback:
    def test_unknown_ability_with_default_require(self) -> None:
        policy = HITLPolicy(require_approval_by_default=True)
        verdict = policy.check_ability("some_unknown_ability")
        assert verdict.approved is False
        assert verdict.reason == "requires_hitl_approval"

    def test_unknown_ability_with_default_approve(self) -> None:
        policy = HITLPolicy(require_approval_by_default=False)
        verdict = policy.check_ability("some_unknown_ability")
        assert verdict.approved is True
        assert verdict.reason == "auto_approved_by_default"

    def test_unknown_ability_with_path_and_default_approve(self) -> None:
        policy = HITLPolicy(
            require_approval_by_default=False,
            allowed_paths=["/tmp/data"],
        )
        verdict = policy.check_ability(
            "some_ability", tool_args={"file_path": "/outside/path"}
        )
        assert verdict.approved is True
        assert verdict.reason == "path_auto_approved_by_default"

    def test_no_manifest_permissions_require_approval(self) -> None:
        policy = HITLPolicy(
            require_approval_by_default=True,
            manifest_permissions={},
        )
        verdict = policy.check_ability("conversation")
        assert verdict.approved is False
        assert verdict.reason == "requires_hitl_approval"

    def test_no_manifest_permissions_default_approve(self) -> None:
        policy = HITLPolicy(
            require_approval_by_default=False,
            manifest_permissions={},
        )
        verdict = policy.check_ability("conversation")
        assert verdict.approved is True
        assert verdict.reason == "auto_approved_by_default"


class TestHITLPolicyPathChecks:
    def test_path_in_allowed_paths(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/data"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/tmp/data/output.txt"}
        )
        assert verdict.approved is True
        assert verdict.reason == "path_in_allowed_scope"

    def test_path_in_workspace(self) -> None:
        policy = HITLPolicy(
            workspace_root="/home/user/project",
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/home/user/project/src/main.py"}
        )
        assert verdict.approved is True

    def test_path_not_in_allowed_scope(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/data"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/etc/passwd"}
        )
        assert verdict.approved is False
        assert verdict.reason == "path_requires_hitl_approval"

    def test_path_not_in_allowed_scope_default_approve(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/data"],
            require_approval_by_default=False,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/etc/passwd"}
        )
        assert verdict.approved is True

    def test_move_file_checks_both_paths(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/dest"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "move_file",
            tool_args={"source_path": "/tmp/dest/src.txt", "destination_path": "/tmp/dest/dst.txt"},
        )
        assert verdict.approved is True

    def test_move_file_source_not_allowed(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/dest"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "move_file",
            tool_args={"source_path": "/etc/secret", "destination_path": "/tmp/dest/file.txt"},
        )
        assert verdict.approved is False

    def test_move_file_dest_not_allowed(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/src"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "move_file",
            tool_args={"source_path": "/tmp/src/file.txt", "destination_path": "/etc/destination"},
        )
        assert verdict.approved is False

    def test_auto_approve_overrides_path_check(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["write_file"],
            allowed_paths=["/safe"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/dangerous/path"}
        )
        assert verdict.approved is True
        assert verdict.reason == "auto_approved"

    def test_workspace_root_normalization(self) -> None:
        policy = HITLPolicy(
            workspace_root="/home/user/project",
        )
        assert policy.workspace_root == os.path.abspath("/home/user/project")

    def test_allowed_paths_normalization(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/data", "/var/log"],
        )
        assert policy.allowed_paths is not None
        assert policy.allowed_paths[0] == os.path.abspath("/tmp/data")

    def test_prefix_matching_not_broader(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/data"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/tmp/database/secret"}
        )
        assert verdict.approved is False

    def test_exact_path_match_allowed(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/data"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/tmp/data"}
        )
        assert verdict.approved is True

    def test_workspace_prefix_not_broader(self) -> None:
        policy = HITLPolicy(
            workspace_root="/home/user/project",
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "write_file", tool_args={"file_path": "/home/user/projectile/evil"}
        )
        assert verdict.approved is False


class TestHITLPolicyManifestProperties:
    def test_manifest_permissions_property(self) -> None:
        perms = {
            "conversation": PermissionFlags(),
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        policy = HITLPolicy(manifest_permissions=perms)
        assert policy.manifest_permissions is perms

    def test_empty_manifest_permissions(self) -> None:
        policy = HITLPolicy(manifest_permissions={})
        assert policy.manifest_permissions == {}
