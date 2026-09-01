from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ghrah.subject.sandbox.executor import CommandResult, SandboxExecutor, SandboxExecutorConfig
from ghrah.subject.sandbox.workspace import (
    SnapshotError,
    SnapshotInfo,
    WorkspaceManager,
)
from ghrah.subject.workspace.providers.git import path_to_locator

requires_git = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not available"
)


class TestCommandResult:
    def test_success(self):
        result = CommandResult(exit_code=0, stdout="ok", stderr="")
        assert result.success is True
        assert result.timed_out is False

    def test_failure_nonzero_exit(self):
        result = CommandResult(exit_code=1, stdout="", stderr="error")
        assert result.success is False

    def test_failure_timed_out(self):
        result = CommandResult(exit_code=0, stdout="", stderr="", timed_out=True)
        assert result.success is False

    def test_defaults(self):
        result = CommandResult(exit_code=0, stdout="out", stderr="err")
        assert result.command == []
        assert result.cwd == ""
        assert result.timed_out is False


class TestSandboxExecutorConfig:
    def test_defaults(self):
        config = SandboxExecutorConfig()
        assert config.default_timeout == 300.0
        assert config.max_output_bytes == 1_000_000
        assert "rm" in config.blocked_commands
        assert "kill" in config.blocked_commands
        assert config.env_overrides == {}

    def test_custom(self):
        config = SandboxExecutorConfig(
            default_timeout=60.0,
            max_output_bytes=500,
            blocked_commands={"dangerous"},
            env_overrides={"FOO": "bar"},
        )
        assert config.default_timeout == 60.0
        assert config.max_output_bytes == 500
        assert config.blocked_commands == {"dangerous"}
        assert config.env_overrides == {"FOO": "bar"}


class TestSandboxExecutorCheckCommand:
    async def test_empty_command(self, tmp_path: Path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        allowed, reason = executor.check_command([])
        assert allowed is False
        assert "Empty" in reason

    async def test_blocked_command(self, tmp_path: Path):
        config = SandboxExecutorConfig(blocked_commands={"rm", "kill"})
        executor = SandboxExecutor(workspace_root=str(tmp_path), config=config)
        allowed, reason = executor.check_command(["rm", "-rf", "/"])
        assert allowed is False
        assert "rm" in reason

    async def test_allowed_command(self, tmp_path: Path):
        config = SandboxExecutorConfig(blocked_commands={"rm"})
        executor = SandboxExecutor(workspace_root=str(tmp_path), config=config)
        allowed, reason = executor.check_command(["git", "status"])
        assert allowed is True
        assert reason == ""

    async def test_blocked_command_with_path(self, tmp_path: Path):
        config = SandboxExecutorConfig(blocked_commands={"shutdown"})
        executor = SandboxExecutor(workspace_root=str(tmp_path), config=config)
        allowed, reason = executor.check_command(["/usr/sbin/shutdown", "-h", "now"])
        assert allowed is False
        assert "shutdown" in reason


class TestSandboxExecutorResolveCwd:
    async def test_none_defaults_to_workspace_root(self, tmp_path: Path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        resolved = executor._resolve_cwd(None)
        assert resolved == str(tmp_path)

    async def test_relative_path(self, tmp_path: Path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        resolved = executor._resolve_cwd("subdir")
        expected = os.path.abspath(os.path.join(str(tmp_path), "subdir"))
        assert resolved == expected

    async def test_absolute_path_inside_workspace(self, tmp_path: Path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        inside_path = os.path.join(str(tmp_path), "subdir")
        resolved = executor._resolve_cwd(inside_path)
        assert resolved == inside_path

    async def test_absolute_path_outside_workspace_raises(self, tmp_path: Path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        outside = str(tmp_path.parent / "outside_sb_dir")
        with pytest.raises(ValueError, match="outside"):
            executor._resolve_cwd(outside)

    async def test_explicit_external_workspace_is_allowed(self, tmp_path: Path):
        executor = SandboxExecutor(workspace_root=str(tmp_path / "internal"))
        external = str(tmp_path / "external")
        executor.allow_external_workspace(external)

        assert executor._resolve_cwd(external) == external
        assert executor._resolve_cwd(os.path.join(external, "nested")) == os.path.join(
            external, "nested"
        )

        executor.disallow_external_workspace(external)
        with pytest.raises(ValueError, match="outside"):
            executor._resolve_cwd(external)

    async def test_relative_path_traversal_raises(self, tmp_path: Path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        with pytest.raises(ValueError, match="outside"):
            executor._resolve_cwd("../../outside_sb_dir")


class TestExternalWorkspaceRegistration:
    @requires_git
    async def test_registers_workspace_outside_manager_root(self, tmp_path: Path):
        internal_root = tmp_path / "subject-root"
        external_workspace = tmp_path / "project-source"
        executor = SandboxExecutor(workspace_root=str(internal_root))
        manager = WorkspaceManager(root_path=str(internal_root), sandbox=executor)
        await manager.start()
        try:
            workspace = await manager.register_workspace(
                path_to_locator(str(external_workspace)), name="source", provider_type="git"
            )
            assert workspace.path == str(external_workspace)
            assert (external_workspace / ".git").is_dir()
        finally:
            await manager.stop()

class TestSandboxExecutorExecuteCommand:
    async def test_execute_echo(self, tmp_path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        await executor.start()
        try:
            result = await executor.execute_command(
                [sys.executable, "-c", "print('hello')"]
            )
            assert result.success is True
            assert "hello" in result.stdout
            assert result.exit_code == 0
        finally:
            await executor.stop()

    async def test_execute_failing_command(self, tmp_path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        await executor.start()
        try:
            result = await executor.execute_command(
                [sys.executable, "-c", "raise SystemExit(1)"]
            )
            assert result.success is False
            assert result.exit_code != 0
        finally:
            await executor.stop()

    async def test_execute_blocked_command(self, tmp_path):
        config = SandboxExecutorConfig(blocked_commands={"rm"})
        executor = SandboxExecutor(workspace_root=str(tmp_path), config=config)
        await executor.start()
        try:
            result = await executor.execute_command(["rm", "-rf", "/"])
            assert result.success is False
            assert "blocked" in result.stderr.lower()
        finally:
            await executor.stop()

    async def test_execute_timeout(self, tmp_path):
        config = SandboxExecutorConfig(default_timeout=1.0)
        executor = SandboxExecutor(workspace_root=str(tmp_path), config=config)
        await executor.start()
        try:
            result = await executor.execute_command(
                [sys.executable, "-c", "import time; time.sleep(10)"]
            )
            assert result.timed_out is True
            assert result.success is False
        finally:
            await executor.stop()

    async def test_execute_with_cwd(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        await executor.start()
        try:
            result = await executor.execute_command(
                [sys.executable, "-c", "import os; print(os.getcwd())"], cwd="subdir"
            )
            assert result.success is True
            assert os.path.normcase(str(subdir)) in os.path.normcase(result.stdout)
        finally:
            await executor.stop()

    async def test_execute_with_env(self, tmp_path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        await executor.start()
        try:
            result = await executor.execute_command(
                [sys.executable, "-c", "import os; print(os.environ['MY_TEST_VAR'])"],
                env={"MY_TEST_VAR": "test_value"},
            )
            assert result.success is True
            assert "test_value" in result.stdout
        finally:
            await executor.stop()

    async def test_execute_with_stdin(self, tmp_path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        await executor.start()
        try:
            result = await executor.execute_command(
                [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
                stdin_data="hello from stdin",
            )
            assert result.success is True
            assert "hello from stdin" in result.stdout
        finally:
            await executor.stop()

    async def test_execute_stderr(self, tmp_path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        await executor.start()
        try:
            result = await executor.execute_command(
                [
                    sys.executable, "-c",
                    "import sys; sys.stderr.write('err\\n'); print('out')",
                ],
            )
            assert result.success is True
            assert "err" in result.stderr
            assert "out" in result.stdout
        finally:
            await executor.stop()

    async def test_execute_not_started_raises(self, tmp_path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        with pytest.raises(RuntimeError, match="not started"):
            await executor.execute_command([sys.executable, "-c", "print('test')"])


class TestSandboxExecutorBuildEnv:
    def test_default_env(self, tmp_path):
        executor = SandboxExecutor(workspace_root=str(tmp_path))
        env = executor._build_env(None)
        assert "PATH" in env

    def test_env_overrides(self, tmp_path):
        config = SandboxExecutorConfig(env_overrides={"MY_VAR": "overridden"})
        executor = SandboxExecutor(workspace_root=str(tmp_path), config=config)
        env = executor._build_env({"MY_VAR": "extra"})
        assert env["MY_VAR"] == "extra"

    def test_config_env_overrides(self, tmp_path):
        config = SandboxExecutorConfig(env_overrides={"MY_VAR": "config_value"})
        executor = SandboxExecutor(workspace_root=str(tmp_path), config=config)
        env = executor._build_env(None)
        assert env["MY_VAR"] == "config_value"


class TestSandboxExecutorTruncateOutput:
    def test_no_truncation(self):
        data = b"hello world"
        text, truncated = SandboxExecutor._truncate_output(data, 1000)
        assert text == "hello world"
        assert truncated is False

    def test_truncation(self):
        data = b"a" * 2000
        text, truncated = SandboxExecutor._truncate_output(data, 1000)
        assert len(text) == 1000
        assert truncated is True


@requires_git
class TestWorkspaceManagerCreate:
    async def test_create_workspace(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        config = SandboxExecutorConfig()
        sandbox = SandboxExecutor(workspace_root=workspace_root, config=config)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            assert os.path.isdir(ws.path)
            assert os.path.isfile(os.path.join(ws.path, ".ghrah-workspace"))
            assert manager.get_workspace("test-agent") is ws
        finally:
            await manager.stop()

    async def test_create_workspace_idempotent(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws1 = await manager.create_workspace("test-agent")
            ws2 = await manager.create_workspace("test-agent")
            assert ws1 is ws2
        finally:
            await manager.stop()

    async def test_create_workspace_without_sandbox_raises(self, tmp_path):
        manager = WorkspaceManager(root_path=str(tmp_path))
        await manager.start()
        try:
            with pytest.raises(SnapshotError, match="SandboxExecutor"):
                await manager.create_workspace("test-agent")
        finally:
            await manager.stop()


@requires_git
class TestWorkspaceManagerDestroy:
    async def test_destroy_workspace(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            ws_path = ws.path
            assert os.path.isdir(ws_path)
            await manager.destroy_workspace("test-agent")
            assert not os.path.exists(ws_path)
            assert manager.get_workspace("test-agent") is None
        finally:
            await manager.stop()

    async def test_destroy_nonexistent_workspace(self, tmp_path):
        manager = WorkspaceManager(root_path=str(tmp_path))
        await manager.destroy_workspace("nonexistent-agent")


@requires_git
class TestWorkspaceManagerLifecycle:
    async def test_start_creates_root(self, tmp_path):
        workspace_root = str(tmp_path / "new_root")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            assert os.path.isdir(workspace_root)
        finally:
            await manager.stop()

    async def test_list_workspaces(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            await manager.create_workspace("agent-1")
            await manager.create_workspace("agent-2")
            names = manager.list_workspaces()
            assert "agent-1" in names
            assert "agent-2" in names
        finally:
            await manager.stop()


@requires_git
class TestAgentWorkspaceSnapshot:
    async def test_snapshot_with_changes(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            test_file = os.path.join(ws.path, "test.txt")
            with open(test_file, "w") as f:
                f.write("hello")

            commit_hash = await ws.snapshot(message="initial file")
            assert len(commit_hash) > 0
        finally:
            await manager.stop()

    async def test_snapshot_no_changes(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            commit1 = await ws.snapshot("first")
            commit2 = await ws.snapshot("no changes")
            assert commit1 == commit2
        finally:
            await manager.stop()


@requires_git
class TestAgentWorkspaceDiff:
    async def test_diff_after_change(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            await ws.snapshot("initial")

            test_file = os.path.join(ws.path, ".ghrah-workspace")
            with open(test_file, "w") as f:
                f.write("modified content")

            diff = await ws.diff()
            assert len(diff) > 0
        finally:
            await manager.stop()

    async def test_diff_against_snapshot(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            snapshot_id = await ws.snapshot("initial")

            marker_file = os.path.join(ws.path, ".ghrah-workspace")
            with open(marker_file, "w") as f:
                f.write("modified content")

            diff = await ws.diff(snapshot_id=snapshot_id)
            assert len(diff) > 0
        finally:
            await manager.stop()


@requires_git
class TestAgentWorkspaceRollback:
    async def test_rollback_restores_files(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")

            test_file = os.path.join(ws.path, "stable.txt")
            with open(test_file, "w") as f:
                f.write("original content")

            snapshot_id = await ws.snapshot("original state")

            with open(test_file, "w") as f:
                f.write("modified content")

            await ws.rollback(snapshot_id)

            with open(test_file) as f:
                assert f.read() == "original content"
        finally:
            await manager.stop()

    async def test_rollback_removes_untracked(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            snapshot_id = await ws.snapshot("before new files")

            new_file = os.path.join(ws.path, "new_untracked.txt")
            with open(new_file, "w") as f:
                f.write("untracked")

            await ws.rollback(snapshot_id)
            assert not os.path.exists(new_file)
        finally:
            await manager.stop()

    async def test_rollback_invalid_snapshot_raises(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            with pytest.raises(SnapshotError):
                await ws.rollback("nonexistent_hash")
        finally:
            await manager.stop()


@requires_git
class TestAgentWorkspaceStatus:
    async def test_status_clean(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            await ws.snapshot("initial")

            status = await ws.status()
            assert status.is_clean is True
        finally:
            await manager.stop()

    async def test_status_with_changes(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")

            new_file = os.path.join(ws.path, "untracked.txt")
            with open(new_file, "w") as f:
                f.write("new")

            status = await ws.status()
            assert status.is_clean is False
            assert len(status.untracked_files) > 0 or len(status.staged_files) > 0
        finally:
            await manager.stop()

    async def test_status_branch(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")
            await ws.snapshot("initial")
            status = await ws.status()
            assert len(status.branch) > 0
        finally:
            await manager.stop()


@requires_git
class TestAgentWorkspaceListSnapshots:
    async def test_list_snapshots(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")

            test_file = os.path.join(ws.path, "file.txt")
            for i in range(3):
                with open(test_file, "w") as f:
                    f.write(f"content v{i}")
                await ws.snapshot(f"commit {i}")

            snapshots = await ws.list_snapshots()
            assert len(snapshots) >= 3
            assert all(isinstance(s, SnapshotInfo) for s in snapshots)
            assert all(len(s.commit_hash) > 0 for s in snapshots)
        finally:
            await manager.stop()

    async def test_list_snapshots_max_count(self, tmp_path):
        workspace_root = str(tmp_path / "workspaces")
        sandbox = SandboxExecutor(workspace_root=workspace_root)
        manager = WorkspaceManager(root_path=workspace_root, sandbox=sandbox)
        await manager.start()
        try:
            ws = await manager.create_workspace("test-agent")

            test_file = os.path.join(ws.path, "file.txt")
            for i in range(5):
                with open(test_file, "w") as f:
                    f.write(f"content v{i}")
                await ws.snapshot(f"commit {i}")

            snapshots = await ws.list_snapshots(max_count=2)
            assert len(snapshots) <= 2
        finally:
            await manager.stop()
