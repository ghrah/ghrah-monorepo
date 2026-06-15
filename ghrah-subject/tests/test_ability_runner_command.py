"""Subject 端命令权限检查和 AbilityRunner execute_command 集成测试。"""

from __future__ import annotations

from ghrah.abilities import CommandSafetyChecker
from ghrah.manifest.types import PermissionFlags

from ghrah.subject.permission_checker import PermissionChecker, PermissionDecision

_EXECUTE_COMMAND_PERMS = PermissionFlags(shell_access=True, require_hitl=True)


class TestPermissionCheckerCommandSafe:
    def test_safe_command_allows(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "ls -la"})
        assert verdict.decision == PermissionDecision.ALLOW

    def test_git_status_allows(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "git status"})
        assert verdict.decision == PermissionDecision.ALLOW

    def test_pytest_allows(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "pytest tests/ -v"})
        assert verdict.decision == PermissionDecision.ALLOW


class TestPermissionCheckerCommandDangerous:
    def test_dangerous_command_denies(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "rm -rf /"})
        assert verdict.decision == PermissionDecision.DENY
        assert verdict.reason == "Dangerous command: rm"

    def test_sudo_denies(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "sudo apt install foo"})
        assert verdict.decision == PermissionDecision.DENY

    def test_git_clean_denies(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "git clean -fdx"})
        assert verdict.decision == PermissionDecision.DENY


class TestPermissionCheckerCommandHitl:
    def test_unknown_command_requires_hitl(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "curl https://example.com"})
        assert verdict.decision == PermissionDecision.REQUIRE_HITL

    def test_git_commit_requires_hitl(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": "git commit -m 'fix'"})
        assert verdict.decision == PermissionDecision.REQUIRE_HITL


class TestPermissionCheckerCommandWorkingDir:
    def test_working_dir_in_workspace_allows(self, tmp_path: object) -> None:
        workspace = str(tmp_path)
        checker = PermissionChecker(
            workspace_root=workspace,
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS},
        )
        verdict = checker.check_ability(
            "execute_command",
            {"command": "ls", "working_dir": workspace},
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_working_dir_outside_workspace_denies(self, tmp_path: object) -> None:
        workspace = str(tmp_path)
        checker = PermissionChecker(
            workspace_root=workspace,
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS},
        )
        verdict = checker.check_ability(
            "execute_command",
            {"command": "ls", "working_dir": "/etc"},
        )
        assert verdict.decision == PermissionDecision.DENY

    def test_no_working_dir_skips_path_check(self) -> None:
        checker = PermissionChecker(
            workspace_root="/workspace",
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS},
        )
        verdict = checker.check_ability(
            "execute_command",
            {"command": "ls"},
        )
        assert verdict.decision == PermissionDecision.ALLOW

    def test_empty_command_denies(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", {"command": ""})
        assert verdict.decision == PermissionDecision.DENY

    def test_command_only_no_tool_args(self) -> None:
        checker = PermissionChecker(
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS}
        )
        verdict = checker.check_ability("execute_command", None)
        assert verdict.decision == PermissionDecision.ALLOW


class TestPermissionCheckerCommandCustom:
    def test_custom_command_checker(self) -> None:
        custom_checker = CommandSafetyChecker(
            safe_commands={"mytool"},
            dangerous_commands={"badtool"},
        )
        checker = PermissionChecker(
            command_checker=custom_checker,
            manifest_permissions={"execute_command": _EXECUTE_COMMAND_PERMS},
        )
        verdict_safe = checker.check_ability("execute_command", {"command": "mytool --version"})
        assert verdict_safe.decision == PermissionDecision.ALLOW

        verdict_danger = checker.check_ability("execute_command", {"command": "badtool --flag"})
        assert verdict_danger.decision == PermissionDecision.DENY


class TestPermissionCheckerWithoutManifest:
    def test_command_without_manifest_returns_allow(self) -> None:
        checker = PermissionChecker()
        verdict = checker.check_ability("execute_command", {"command": "rm -rf /"})
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_read_file_without_manifest_returns_allow(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/safe"], require_approval=False)
        verdict = checker.check_ability("read_file", {"file_path": "/etc/passwd"})
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"

    def test_write_file_without_manifest_returns_allow(self) -> None:
        checker = PermissionChecker(allowed_paths=["/tmp/safe"], require_approval=True)
        verdict = checker.check_ability("write_file", {"file_path": "/etc/passwd"})
        assert verdict.decision == PermissionDecision.ALLOW
        assert verdict.reason == "no_path_security_concern"


# ── AbilityRunner execute_command working_dir 解析测试 ──


class TestAbilityRunnerWorkingDir:
    def test_working_dir_resolved_for_execute_command(self) -> None:
        from ghrah.subject.ability_runner import AbilityRunner

        runner = AbilityRunner.__new__(AbilityRunner)
        runner._workspace_resolver = lambda name: f"/workspace/{name}"

        result = runner._resolve_paths(
            "execute_command",
            {"command": "ls", "working_dir": "src"},
            "agent1",
        )
        assert result["working_dir"] == "/workspace/agent1/src"

    def test_working_dir_absolute_not_resolved(self) -> None:
        from ghrah.subject.ability_runner import AbilityRunner

        runner = AbilityRunner.__new__(AbilityRunner)
        runner._workspace_resolver = lambda name: f"/workspace/{name}"

        result = runner._resolve_paths(
            "execute_command",
            {"command": "ls", "working_dir": "/absolute/path"},
            "agent1",
        )
        assert result["working_dir"] == "/absolute/path"

    def test_working_dir_not_resolved_for_other_abilities(self) -> None:
        from ghrah.subject.ability_runner import AbilityRunner

        runner = AbilityRunner.__new__(AbilityRunner)
        runner._workspace_resolver = lambda name: f"/workspace/{name}"

        result = runner._resolve_paths(
            "read_file",
            {"file_path": "src/main.py"},
            "agent1",
        )
        assert result["file_path"] == "/workspace/agent1/src/main.py"
        assert "working_dir" not in result
