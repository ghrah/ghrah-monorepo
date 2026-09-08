# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace 资源模型 + provider 抽象 + 注册表（挂载语义）。

挂载语义：workspace 收敛为「登记 + 授权 + 解挂」，对挂载目录零物理操作。
store 是唯一注册真相；legacy GitWorkspaceProvider 与 marker 机制已移除
（快照需求由 shadow-git checkpoint 库承接，backlog）。
"""

from __future__ import annotations

from ghrah.subject.workspace.errors import SnapshotError, WorkspaceProviderError
from ghrah.subject.workspace.locator import locator_to_path, path_to_locator
from ghrah.subject.workspace.models import WorkspaceRecord, WorkspaceStatus
from ghrah.subject.workspace.providers.base import WorkspaceCaps, WorkspaceProvider
from ghrah.subject.workspace.providers.plain import PlainWorkspaceProvider
from ghrah.subject.workspace.registry import ProviderRegistry, build_default_registry
from ghrah.subject.workspace.store import WorkspaceStore

__all__ = [
    "PlainWorkspaceProvider",
    "ProviderRegistry",
    "SnapshotError",
    "WorkspaceCaps",
    "WorkspaceProvider",
    "WorkspaceProviderError",
    "WorkspaceRecord",
    "WorkspaceStatus",
    "WorkspaceStore",
    "build_default_registry",
    "locator_to_path",
    "path_to_locator",
]
