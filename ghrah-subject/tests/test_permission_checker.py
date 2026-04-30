from __future__ import annotations

import os

from ghrah.manifest.types import PermissionFlags

from ghrah.subject.permission_checker import (
    PermissionChecker,
    PermissionDecision,
)


class TestPermissionCheckerReadPaths:
    def test_no_restrictions_allows_all_reads(self) -> None:
        checker = PermissionChecker(allowed_paths=None, workspace_root=None)
        allowed, reason = checker.check_read_path("/any/path/file.txt")
        assert allowed is True
        assert reason == ""

    def test_allowed_path_allows_read(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data"])
        allowed, reason = checker.check_read_path("/tmp/data/file.txt")
        assert allowed is True
        assert reason == ""

    def test_workspace_root_allows_read(self) -> None:
        checker = PermissionChecker(workspace_root="/home/user/project")
        allowed, reason = checker.check_read_path("/home/user/project/src/main.py")
        assert allowed is True

    def test_outside_path_denied(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data"])
        allowed, reason = checker.check_read_path("/etc/passwd")
        assert allowed is False
        assert "Permission denied" in reason

    def test_exact_path_match_allowed(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data"])
        allowed, reason = checker.check_read_path("/tmp/data")
        assert allowed is True

    def test_prefix_not_broader(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data"])
        allowed, _ = checker.check_read_path("/tmp/database/secret")
        assert allowed is False


class TestPermissionCheckerWritePaths:
    def test_no_restrictions_require_approval(self) -> None:
        checker = PermissionChecker(
            allowed_paths=None, workspace_root=None, require_approval=True
        )
        allowed, status = checker.check_write_path("/any/path/file.txt")
        assert allowed is True
        assert status == "pending"

    def test_no_restrictions_auto_approve(self) -> None:
        checker = PermissionChecker(
            allowed_paths=None, workspace_root=None, require_approval=False
        )
        allowed, status = checker.check_write_path("/any/path/file.txt")
        assert allowed is True
        assert status is None

    def test_allowed_path_auto_approved(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data"])
        allowed, status = checker.check_write_path("/tmp/data/output.txt")
        assert allowed is True
        assert status is None

    def test_workspace_root_auto_approved(self) -> None:
        checker = PermissionChecker(workspace_root="/home/user/project")
        allowed, status = checker.check_write_path("/home/user/project/src/new.py")
        assert allowed is True
        assert status is None

    def test_outside_path_require_approval(self) -> None:
        checker = PermissionChecker(
            allowed_paths=["/tmp/data"], require_approval=True
        )
        allowed, status = checker.check_write_path("/etc/config.ini")
        assert allowed is True
        assert status == "pending"

    def test_outside_path_no_approval_denied(self) -> None:
        checker = PermissionChecker(
            allowed_paths=["/tmp/data"], require_approval=False
        )
        allowed, status = checker.check_write_path("/etc/config.ini")
        assert allowed is False
        assert status is not None
        assert "Permission denied" in status


class TestPermissionCheckerManifestAbilities:
    def test_conversation_no_path_concern(self) -> None:
        manifest_perms = {
            "conversation": PermissionFlags(),
        }
        checker = PermissionChecker(manifest_permissions=manifest_perms)
        verdict = checker.check_ability("conversation")
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_end_task_no_path_concern(self) -> None:
        manifest_perms = {
            "end_task": PermissionFlags(),
        }
        checker = PermissionChecker(manifest_permissions=manifest_perms)
        verdict = checker.check_ability("end_task")
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_read_file_manifest_read_path(self) -> None:
        manifest_perms = {
            "read_file": PermissionFlags(fs_read_only=True),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/data"],
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "read_file", {"file_path": "/tmp/data/input.txt"}
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_read_file_manifest_denied_path(self) -> None:
        manifest_perms = {
            "read_file": PermissionFlags(
                fs_read_only=True,
                denied_paths=["/etc/shadow"],
            ),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/data"],
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "read_file", {"file_path": "/etc/shadow"}
        )
        assert verdict.decision == PermissionDecision.DENY
        assert "denied by manifest" in verdict.reason.lower()

    def test_write_file_manifest_allowed_path(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"],
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "write_file", {"file_path": "/tmp/safe/output.txt"}
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_write_file_manifest_outside_path_require_hitl(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"], require_approval=True,
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "write_file", {"file_path": "/etc/config.ini"}
        )
        assert verdict.decision == PermissionDecision.REQUIRE_HITL

    def test_write_file_manifest_outside_path_denied(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"], require_approval=False,
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "write_file", {"file_path": "/etc/config.ini"}
        )
        assert verdict.decision == PermissionDecision.DENY

    def test_write_file_manifest_denied_path(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(
                fs_write=True,
                require_hitl=True,
                denied_paths=["/etc"],
            ),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"],
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "write_file", {"file_path": "/etc/config.ini"}
        )
        assert verdict.decision == PermissionDecision.DENY
        assert "denied by manifest" in verdict.reason.lower()

    def test_execute_command_manifest_safe_command(self) -> None:
        manifest_perms = {
            "execute_command": PermissionFlags(shell_access=True, require_hitl=True),
        }
        checker = PermissionChecker(manifest_permissions=manifest_perms)
        verdict = checker.check_ability(
            "execute_command", {"command": "ls -la", "working_dir": "/tmp"}
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_execute_command_manifest_denied_command(self) -> None:
        manifest_perms = {
            "execute_command": PermissionFlags(
                shell_access=True,
                require_hitl=True,
                denied_commands=["rm -rf"],
            ),
        }
        checker = PermissionChecker(manifest_permissions=manifest_perms)
        verdict = checker.check_ability(
            "execute_command", {"command": "rm -rf /"}
        )
        assert verdict.decision == PermissionDecision.DENY
        assert "denied by manifest" in verdict.reason.lower()

    def test_unknown_ability_returns_allow(self) -> None:
        checker = PermissionChecker(require_approval=True)
        verdict = checker.check_ability("unknown_ability")
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_unknown_ability_auto_approved(self) -> None:
        checker = PermissionChecker(require_approval=False)
        verdict = checker.check_ability("unknown_ability")
        assert verdict.decision == PermissionDecision.ALLOW


class TestPermissionCheckerLegacyCompat:
    def test_no_manifest_write_ability_path_check(self) -> None:
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"], require_approval=True,
            manifest_permissions={},
        )
        verdict = checker.check_ability("write_file", {"file_path": "/tmp/safe/out.txt"})
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_move_file_checks_both_paths_src_denied(self) -> None:
        manifest_perms = {
            "move_file": PermissionFlags(fs_write=True, fs_read_only=True, require_hitl=True),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/dest"], require_approval=False,
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "move_file",
            {"source_path": "/etc/secret", "destination_path": "/tmp/dest/file.txt"},
        )
        assert verdict.decision == PermissionDecision.DENY

    def test_move_file_checks_both_paths_dst_requires_hitl(self) -> None:
        manifest_perms = {
            "move_file": PermissionFlags(fs_write=True, fs_read_only=True, require_hitl=True),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/src"], require_approval=True,
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "move_file",
            {"source_path": "/tmp/src/file.txt", "destination_path": "/etc/destination"},
        )
        assert verdict.decision == PermissionDecision.REQUIRE_HITL

    def test_move_file_both_paths_allowed(self) -> None:
        manifest_perms = {
            "move_file": PermissionFlags(fs_write=True, fs_read_only=True, require_hitl=True),
        }
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"],
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability(
            "move_file",
            {"source_path": "/tmp/safe/src.txt", "destination_path": "/tmp/safe/dst.txt"},
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_no_tool_args_write_ability_returns_allow(self) -> None:
        manifest_perms = {
            "write_file": PermissionFlags(fs_write=True, require_hitl=True),
        }
        checker = PermissionChecker(
            require_approval=True,
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability("write_file")
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_no_tool_args_read_ability_returns_allow(self) -> None:
        manifest_perms = {
            "read_file": PermissionFlags(fs_read_only=True),
        }
        checker = PermissionChecker(
            require_approval=True,
            manifest_permissions=manifest_perms,
        )
        verdict = checker.check_ability("read_file")
        assert verdict.decision == PermissionDecision.ALLOW


class TestPermissionCheckerProperties:
    def test_allowed_paths_normalization(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data", "/var/log"])
        assert checker.allowed_paths is not None
        assert checker.allowed_paths[0] == os.path.abspath("/tmp/data")
        assert checker.allowed_paths[1] == os.path.abspath("/var/log")

    def test_workspace_root_normalization(self) -> None:
        checker = PermissionChecker(workspace_root="/home/user/project")
        assert checker.workspace_root == os.path.abspath("/home/user/project")

    def test_none_paths(self) -> None:
        checker = PermissionChecker()
        assert checker.allowed_paths is None
        assert checker.workspace_root is None
