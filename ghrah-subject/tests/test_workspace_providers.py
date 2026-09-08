# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""PlainWorkspaceProvider / ProviderRegistry 单测（挂载语义）。

- plain provider：init 仅 mkdir（零 marker、零 git）、status 存在性/可写性；
- registry：register/get/detect（file:// 可解析 → plain；未知类型报错）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.workspace import (
    PlainWorkspaceProvider,
    ProviderRegistry,
    WorkspaceCaps,
    WorkspaceProviderError,
    WorkspaceRecord,
    build_default_registry,
    locator_to_path,
    path_to_locator,
)


def _plain_record(ws_path: str, name: str = "data") -> WorkspaceRecord:
    return WorkspaceRecord(
        name=name,
        provider_type="plain",
        locator=path_to_locator(ws_path),
    )


# ─── PlainWorkspaceProvider ───


class TestPlainWorkspaceProvider:
    async def test_init_creates_dir_without_marker_or_git(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        ws_path = str(tmp_path / "data")
        record = _plain_record(ws_path)
        await provider.init(record)
        assert os.path.isdir(ws_path)
        # 挂载语义：零 marker、零 git
        assert not os.path.exists(os.path.join(ws_path, ".ghrah-workspace"))
        assert not os.path.exists(os.path.join(ws_path, ".git"))

    async def test_init_idempotent_preserves_content(self, tmp_path: Path) -> None:
        provider = PlainWorkspaceProvider()
        ws_path = str(tmp_path / "data")
        record = _plain_record(ws_path)
        await provider.init(record)
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

    async def test_caps_filesystem_backed_only(self) -> None:
        provider = PlainWorkspaceProvider()
        assert provider.provider_type == "plain"
        assert WorkspaceCaps.FILESYSTEM_BACKED in provider.capabilities
        assert provider.capabilities == WorkspaceCaps.FILESYSTEM_BACKED


# ─── ProviderRegistry ───


class TestProviderRegistry:
    def test_get_unknown_raises(self) -> None:
        registry = ProviderRegistry()
        with pytest.raises(WorkspaceProviderError):
            registry.get("nope")

    def test_get_git_raises_after_legacy_removal(self) -> None:
        registry = build_default_registry(SandboxExecutor(workspace_root="/tmp/unused"))
        with pytest.raises(WorkspaceProviderError):
            registry.get("git")

    def test_register_and_get(self) -> None:
        provider = PlainWorkspaceProvider()
        registry = ProviderRegistry()
        registry.register(provider)
        assert registry.get("plain") is provider
        assert registry.has("plain")
        assert "plain" in registry.types()

    def test_build_default_registry_plain_only(self) -> None:
        registry = build_default_registry(SandboxExecutor(workspace_root="/tmp/unused"))
        assert registry.types() == ["plain"]
        assert isinstance(registry.get("plain"), PlainWorkspaceProvider)

    def test_detect_file_locator_returns_plain(self, tmp_path: Path) -> None:
        registry = build_default_registry(SandboxExecutor(workspace_root="/tmp/unused"))
        # 挂载语义：不探测目录内容（无 marker/.git 探测），file:// 可解析即 plain
        detected = registry.detect(path_to_locator(str(tmp_path / "some-dir")))
        assert isinstance(detected, PlainWorkspaceProvider)

    def test_detect_existing_git_dir_returns_plain(self, tmp_path: Path) -> None:
        """有 .git 的目录也按 plain 登记（不探测内容；git 归属用户流程）。"""
        registry = build_default_registry(SandboxExecutor(workspace_root="/tmp/unused"))
        gitdir = str(tmp_path / "gitdir")
        os.makedirs(os.path.join(gitdir, ".git"))
        detected = registry.detect(path_to_locator(gitdir))
        assert isinstance(detected, PlainWorkspaceProvider)

    def test_detect_non_file_locator_returns_none(self) -> None:
        registry = build_default_registry(SandboxExecutor(workspace_root="/tmp/unused"))
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
