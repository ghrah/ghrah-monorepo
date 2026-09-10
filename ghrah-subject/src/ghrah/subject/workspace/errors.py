# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace provider 错误类型。"""

from __future__ import annotations

__all__ = ["SnapshotError", "WorkspaceProviderError"]


class WorkspaceProviderError(Exception):
    """Workspace provider 操作错误（init/status/注册校验）。"""


class SnapshotError(WorkspaceProviderError):
    """快照操作错误（legacy git 版本能力专用；现仅作兼容 re-export 保留，
    挂载语义下 snapshot/rollback/diff 已整体移除）。

    兼容层 re-export 此名以保持既有调用方零改动。
    """
