from __future__ import annotations

import os

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


class TestPermissionCheckerCheckAbility:
    def test_write_ability_allowed_path(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/safe"])
        verdict = checker.check_ability(
            "write_file", {"file_path": "/tmp/safe/output.txt"}
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_write_ability_outside_path_require_hitl(self) -> None:
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"], require_approval=True
        )
        verdict = checker.check_ability(
            "write_file", {"file_path": "/etc/config.ini"}
        )
        assert verdict.decision == PermissionDecision.REQUIRE_HITL

    def test_write_ability_outside_path_denied(self) -> None:
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"], require_approval=False
        )
        verdict = checker.check_ability(
            "write_file", {"file_path": "/etc/config.ini"}
        )
        assert verdict.decision == PermissionDecision.DENY

    def test_read_ability_allowed_path(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data"])
        verdict = checker.check_ability(
            "read_file", {"file_path": "/tmp/data/input.txt"}
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_read_ability_outside_path_denied(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/data"])
        verdict = checker.check_ability(
            "read_file", {"file_path": "/etc/passwd"}
        )
        assert verdict.decision == PermissionDecision.DENY

    def test_unknown_ability_returns_allow(self) -> None:
        checker = PermissionChecker(require_approval=True)
        verdict = checker.check_ability("unknown_ability")
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_unknown_ability_auto_approved(self) -> None:
        checker = PermissionChecker(require_approval=False)
        verdict = checker.check_ability("unknown_ability")
        assert verdict.decision == PermissionDecision.ALLOW

    def test_move_file_checks_both_paths_src_denied(self) -> None:
        checker = PermissionChecker(
            allowed_paths=["/tmp/dest"], require_approval=False
        )
        verdict = checker.check_ability(
            "move_file",
            {"file_path": "/etc/secret", "destination_path": "/tmp/dest/file.txt"},
        )
        assert verdict.decision == PermissionDecision.DENY

    def test_move_file_checks_both_paths_dst_requires_hitl(self) -> None:
        checker = PermissionChecker(
            allowed_paths=["/tmp/src"], require_approval=True
        )
        verdict = checker.check_ability(
            "move_file",
            {"file_path": "/tmp/src/file.txt", "destination_path": "/etc/destination"},
        )
        assert verdict.decision == PermissionDecision.REQUIRE_HITL

    def test_move_file_both_paths_allowed(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/safe"])
        verdict = checker.check_ability(
            "move_file",
            {"file_path": "/tmp/safe/src.txt", "destination_path": "/tmp/safe/dst.txt"},
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_no_tool_args_write_ability_returns_allow(self) -> None:
        checker = PermissionChecker(require_approval=True)
        verdict = checker.check_ability("write_file")
        assert verdict.decision == PermissionDecision.ALLOW

    def test_no_tool_args_read_ability_returns_allow(self) -> None:
        checker = PermissionChecker(require_approval=True)
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
