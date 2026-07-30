# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace provider 包。

W1 阶段：models + ABC 基座。后续 W2-W5 在此包下补 git/plain provider、
registry、store、manager。
"""

from __future__ import annotations

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

__all__ = [
    "AdoptResult",
    "SnapshotInfo",
    "VersionedWorkspaceProvider",
    "WorkspaceCaps",
    "WorkspaceProvider",
    "WorkspaceRecord",
    "WorkspaceStatus",
]
