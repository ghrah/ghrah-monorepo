# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""GitWorkspaceProvider / PlainWorkspaceProvider / ProviderRegistry 单测。

W2/W3 验收：git provider 版本能力（snapshot/rollback/diff/status/list_snapshots）+
plain provider init/adopt/status/destroy + registry register/get/detect。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.workspace import (
    GitWorkspaceProvider,
    PlainWorkspaceProvider,
    ProviderRegistry,
    SnapshotInfo,
    WorkspaceCaps,
    WorkspaceProviderError,
    WorkspaceRecord,
    build_default_registry,
    locator_to_path,
    path_to_locator,
)
from ghrah.subject.workspace.marker import MARKER_FILENAME, read_marker


def _record(ws_path: str, name: str = "test-agent") -> WorkspaceRecord:
    return WorkspaceRecord(
        name=name,
        provider_type="git",
        locator=path_to_locator(ws_path),
    )


def _plain_record(ws_path: str, name: str = "data") -> WorkspaceRecord:
    return WorkspaceRecord(
        name=name,
        provider_type="plain",
        locator=path_to_locator(ws_path),
    )


class _Sandbox:
    """Helper: start/stop SandboxExecutor in tests."""

    def __init__(self, root: str) -> None:
        self.executor = SandboxExecutor(workspace_root=root)

    async def __aenter__(self) -> SandboxExecutor:
        await self.executor.start()
        return self.executor

    async def __aexit__(self, *exc: object) -> None:
        await self.executor.stop()


# ─── GitWorkspaceProvider ───


class TestGitWorkspaceProviderInit:
    async def test_init_creates_repo_and_marker(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            ws_path = os.path.join(root, "agent-x")
            record = _record(ws_path)
            await provider.init(record)
            assert os.path.isdir(os.path.join(ws_path, ".git"))
            assert os.path.isfile(os.path.join(ws_path, MARKER_FILENAME))
            marker = read_marker(ws_path)
            assert marker is not None
            assert marker.workspace_id == record.workspace_id
            assert marker.provider_type == "git"
            assert marker.subject_id == "default"

    async def test_init_idempotent_on_marker_match(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            ws_path = os.path.join(root, "agent-x")
            record = _record(ws_path)
            await provider.init(record)
            # 写入一个文件并提交，init 不应破坏
            f = os.path.join(ws_path, "kept.txt")
            with open(f, "w") as fh:
                fh.write("data")
            await sandbox.execute_command(["git", "add", "-A"], cwd=ws_path)
            await sandbox.execute_command(["git", "commit", "-m", "keep"], cwd=ws_path)
            await provider.init(record)
            assert os.path.isfile(f)


class TestGitWorkspaceProviderVersioned:
    async def test_snapshot_returns_hash_and_diff(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            ws_path = os.path.join(root, "agent")
            record = _record(ws_path)
            await provider.init(record)

            with open(os.path.join(ws_path, "a.txt"), "w") as fh:
                fh.write("hello")
            h = await provider.snapshot(record, message="add a")
            assert len(h) > 0
            diff = await provider.diff(record)
            assert "a.txt" in diff or diff == ""

    async def test_snapshot_no_changes_returns_head(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(os.path.join(root, "agent"))
            await provider.init(record)
            h1 = await provider.snapshot(record, "first")
            h2 = await provider.snapshot(record, "no changes")
            assert h1 == h2

    async def test_rollback_restores_files(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(os.path.join(root, "agent"))
            await provider.init(record)
            stable = os.path.join(locator_to_path(record.locator), "stable.txt")
            with open(stable, "w") as fh:
                fh.write("original")
            snap = await provider.snapshot(record, "original")
            with open(stable, "w") as fh:
                fh.write("modified")
            await provider.rollback(record, snap)
            with open(stable) as fh:
                assert fh.read() == "original"

    async def test_rollback_invalid_raises(self, tmp_path: Path) -> None:
        from ghrah.subject.workspace import SnapshotError

        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(os.path.join(root, "agent"))
            await provider.init(record)
            with pytest.raises(SnapshotError):
                await provider.rollback(record, "nonexistent_hash")

    async def test_status_reports_git_state(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(os.path.join(root, "agent"))
            await provider.init(record)
            status = await provider.status(record)
            assert status.exists is True
            assert status.extra["is_clean"] in (True, False)
            assert status.extra["branch"]

    async def test_status_missing_dir(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(str(tmp_path / "nope"))
            status = await provider.status(record)
            assert status.exists is False

    async def test_list_snapshots(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(os.path.join(root, "agent"))
            await provider.init(record)
            f = os.path.join(locator_to_path(record.locator), "f.txt")
            for i in range(3):
                with open(f, "w") as fh:
                    fh.write(f"v{i}")
                await provider.snapshot(record, f"commit {i}")
            snaps = await provider.list_snapshots(record)
            assert len(snaps) >= 3
            assert all(isinstance(s, SnapshotInfo) for s in snaps)

    async def test_list_snapshots_max_count(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(os.path.join(root, "agent"))
            await provider.init(record)
            f = os.path.join(locator_to_path(record.locator), "f.txt")
            for i in range(5):
                with open(f, "w") as fh:
                    fh.write(f"v{i}")
                await provider.snapshot(record, f"commit {i}")
            snaps = await provider.list_snapshots(record, max_count=2)
            assert len(snaps) <= 2

    async def test_destroy_removes_dir(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            record = _record(os.path.join(root, "agent"))
            await provider.init(record)
            ws_path = locator_to_path(record.locator)
            await provider.destroy(record)
            assert not os.path.exists(ws_path)


class TestGitWorkspaceProviderAdopt:
    async def test_adopt_marker_match(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            ws_path = os.path.join(root, "agent")
            record = _record(ws_path)
            await provider.init(record)
            result = await provider.adopt(path_to_locator(ws_path))
            assert result is not None
            assert result.workspace_id == record.workspace_id
            assert result.provider_type == "git"
            assert result.subject_id == "default"

    async def test_adopt_no_marker_returns_none(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            bare = str(tmp_path / "bare")
            os.makedirs(bare)
            assert await provider.adopt(path_to_locator(bare)) is None

    async def test_adopt_legacy_marker_returns_none(self, tmp_path: Path) -> None:
        root = str(tmp_path / "wsroot")
        async with _Sandbox(root) as sandbox:
            provider = GitWorkspaceProvider(sandbox)
            legacy = str(tmp_path / "legacy")
            os.makedirs(legacy)
            with open(os.path.join(legacy, MARKER_FILENAME), "w") as fh:
                fh.write("# Workspace for agent: legacy\n")
            assert await provider.adopt(path_to_locator(legacy)) is None


# ─── PlainWorkspaceProvider ───


class TestPlainWorkspaceProvider:
    async def test_init_creates_dir_and_marker(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        ws_path = str(tmp_path / "data")
        record = _plain_record(ws_path)
        await provider.init(record)
        assert os.path.isdir(ws_path)
        marker = read_marker(ws_path)
        assert marker is not None
        assert marker.provider_type == "plain"

    async def test_init_idempotent_on_marker_match(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        ws_path = str(tmp_path / "data")
        record = _plain_record(ws_path)
        await provider.init(record)
        # 写文件不应被破坏
        f = os.path.join(ws_path, "x.txt")
        with open(f, "w") as fh:
            fh.write("keep")
        await provider.init(record)
        assert os.path.isfile(f)

    async def test_status(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        ws_path = str(tmp_path / "data")
        record = _plain_record(ws_path)
        await provider.init(record)
        status = await provider.status(record)
        assert status.exists is True
        assert status.writable is True
        assert status.extra == {}

    async def test_status_missing(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        record = _plain_record(str(tmp_path / "nope"))
        status = await provider.status(record)
        assert status.exists is False

    async def test_destroy(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        ws_path = str(tmp_path / "data")
        record = _plain_record(ws_path)
        await provider.init(record)
        await provider.destroy(record)
        assert not os.path.exists(ws_path)

    async def test_adopt_marker_match(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        ws_path = str(tmp_path / "data")
        record = _plain_record(ws_path)
        await provider.init(record)
        result = await provider.adopt(path_to_locator(ws_path))
        assert result is not None
        assert result.provider_type == "plain"

    async def test_no_version_capabilities(self) -> None:
        provider = PlainWorkspaceProvider()
        assert provider.provider_type == "plain"
        assert WorkspaceCaps.SNAPSHOT not in provider.capabilities
        assert WorkspaceCaps.ROLLBACK not in provider.capabilities
        assert WorkspaceCaps.DIFF not in provider.capabilities
        assert WorkspaceCaps.FILESYSTEM_BACKED in provider.capabilities


# ─── ProviderRegistry ───


class TestProviderRegistry:
    def test_get_unknown_raises(self) -> None:
        registry = ProviderRegistry()
        with pytest.raises(WorkspaceProviderError):
            registry.get("nope")

    def test_register_and_get(self, tmp_path: Path) -> None:
        sandbox = SandboxExecutor(workspace_root=str(tmp_path / "root"))
        provider = GitWorkspaceProvider(sandbox)
        registry = ProviderRegistry()
        registry.register(provider)
        assert registry.get("git") is provider
        assert registry.has("git")
        assert "git" in registry.types()

    def test_build_default_registry_has_git_and_plain(self, tmp_path: Path) -> None:
        sandbox = SandboxExecutor(workspace_root=str(tmp_path / "root"))
        registry = build_default_registry(sandbox)
        assert registry.has("git")
        assert registry.has("plain")
        assert isinstance(registry.get("git"), GitWorkspaceProvider)
        assert isinstance(registry.get("plain"), PlainWorkspaceProvider)

    def test_detect_marker_provider_type(self, tmp_path: Path) -> None:
        sandbox = SandboxExecutor(workspace_root=str(tmp_path / "root"))
        registry = build_default_registry(sandbox)
        # 构造一个带 plain marker 的目录
        plain_path = str(tmp_path / "plaindir")
        os.makedirs(plain_path)
        record = _plain_record(plain_path)
        # plain provider init 需要 await，这里直接写 marker
        from ghrah.subject.workspace.marker import write_marker

        write_marker(plain_path, record)
        detected = registry.detect(path_to_locator(plain_path))
        assert isinstance(detected, PlainWorkspaceProvider)

    def test_detect_no_marker_git_dir(self, tmp_path: Path) -> None:
        sandbox = SandboxExecutor(workspace_root=str(tmp_path / "root"))
        registry = build_default_registry(sandbox)
        gitdir = str(tmp_path / "gitdir")
        os.makedirs(os.path.join(gitdir, ".git"))
        detected = registry.detect(path_to_locator(gitdir))
        assert isinstance(detected, GitWorkspaceProvider)

    def test_detect_no_marker_plain_dir(self, tmp_path: Path) -> None:
        sandbox = SandboxExecutor(workspace_root=str(tmp_path / "root"))
        registry = build_default_registry(sandbox)
        plain = str(tmp_path / "plain")
        os.makedirs(plain)
        detected = registry.detect(path_to_locator(plain))
        assert isinstance(detected, PlainWorkspaceProvider)

    def test_detect_non_file_locator_returns_none(self, tmp_path: Path) -> None:
        sandbox = SandboxExecutor(workspace_root=str(tmp_path / "root"))
        registry = build_default_registry(sandbox)
        assert registry.detect("nfs://host/share") is None


class TestLocatorHelpers:
    def test_roundtrip(self, tmp_path: Path) -> None:
        p = str(tmp_path / "abs" / "path")
        loc = path_to_locator(p)
        assert loc.startswith("file://")
        assert locator_to_path(loc) == p

    def test_locator_to_path_non_file_raises(self) -> None:
        with pytest.raises(ValueError):
            locator_to_path("nfs://host/share")
