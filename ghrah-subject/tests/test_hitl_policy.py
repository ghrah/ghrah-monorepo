from __future__ import annotations

import os

from ghrah.subject.hitl.policy import HITLPolicy


class TestHITLPolicy:
    def test_auto_approve_ability(self) -> None:
        policy = HITLPolicy(auto_approve_abilities=["read_file", "list_dir"])
        verdict = policy.check_ability("read_file")
        assert verdict.approved is True
        assert verdict.reason == "auto_approved"

    def test_auto_approve_ability_not_in_list(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["read_file"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability("write_file")
        assert verdict.approved is False
        assert verdict.reason == "requires_hitl_approval"

    def test_default_approve_when_not_required(self) -> None:
        policy = HITLPolicy(require_approval_by_default=False)
        verdict = policy.check_ability("write_file")
        assert verdict.approved is True
        assert verdict.reason == "auto_approved_by_default"

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

    def test_no_tool_args_with_default_approval(self) -> None:
        policy = HITLPolicy(require_approval_by_default=True)
        verdict = policy.check_ability("some_ability")
        assert verdict.approved is False

    def test_no_tool_args_without_default_approval(self) -> None:
        policy = HITLPolicy(require_approval_by_default=False)
        verdict = policy.check_ability("some_ability")
        assert verdict.approved is True

    def test_move_file_checks_both_paths(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/dest"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "move_file",
            tool_args={"file_path": "/tmp/dest/src.txt", "destination_path": "/tmp/dest/dst.txt"},
        )
        assert verdict.approved is True

    def test_move_file_source_not_allowed(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/dest"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "move_file",
            tool_args={"file_path": "/etc/secret", "destination_path": "/tmp/dest/file.txt"},
        )
        assert verdict.approved is False

    def test_move_file_dest_not_allowed(self) -> None:
        policy = HITLPolicy(
            allowed_paths=["/tmp/src"],
            require_approval_by_default=True,
        )
        verdict = policy.check_ability(
            "move_file",
            tool_args={"file_path": "/tmp/src/file.txt", "destination_path": "/etc/destination"},
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
