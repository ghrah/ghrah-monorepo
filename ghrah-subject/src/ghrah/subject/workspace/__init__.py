# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace 资源模型 + provider 抽象 + 注册表。

W1-W3 阶段：models + ABC + git/plain provider + registry。
后续 W4-W5 在此包下补 store、manager。
"""

from __future__ import annotations

from ghrah.subject.workspace.errors import SnapshotError, WorkspaceProviderError
from ghrah.subject.workspace.marker import MARKER_FILENAME, MarkerData
from ghrah.subject.workspace.models import (
    AdoptResult,
    SnapshotInfo,
    WorkspaceRecord,
    WorkspaceStatus,
)
from ghrah.subject.workspace.providers.base import (
    VersionedWorkspaceProvider,
    WorkspaceCaps,
    WorkspaceProvider,
)
from ghrah.subject.workspace.providers.git import (
    GitWorkspaceProvider,
    locator_to_path,
    path_to_locator,
)
from ghrah.subject.workspace.providers.plain import PlainWorkspaceProvider
from ghrah.subject.workspace.registry import ProviderRegistry, build_default_registry

__all__ = [
    "AdoptResult",
    "GitWorkspaceProvider",
    "MARKER_FILENAME",
    "MarkerData",
    "PlainWorkspaceProvider",
    "ProviderRegistry",
    "SnapshotError",
    "SnapshotInfo",
    "VersionedWorkspaceProvider",
    "WorkspaceCaps",
    "WorkspaceProvider",
    "WorkspaceProviderError",
    "WorkspaceRecord",
    "WorkspaceStatus",
    "build_default_registry",
    "locator_to_path",
    "path_to_locator",
]
