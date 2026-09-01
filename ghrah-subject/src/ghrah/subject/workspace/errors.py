# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace provider 错误类型。"""

from __future__ import annotations

__all__ = ["SnapshotError", "WorkspaceProviderError"]


class WorkspaceProviderError(Exception):
    """Workspace provider 操作错误（init/adopt/status/destroy/版本能力）。"""


class SnapshotError(WorkspaceProviderError):
    """快照操作错误（git provider 版本能力专用）。

    沿用旧 :class:`ghrah.subject.sandbox.workspace.SnapshotError` 语义，
    兼容层 re-export 此名以保持现有调用方零改动。
    """
