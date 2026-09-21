# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""内核异常：乐观锁冲突与 Denial。"""

from __future__ import annotations

from ghrah.taskstore.models import VerificationGaps

__all__ = [
    "ConcurrentModificationError",
    "DenialError",
    "TaskNotFoundError",
]


class ConcurrentModificationError(Exception):
    """乐观锁：expected_version 与当前 version 不匹配。"""


class TaskNotFoundError(Exception):
    """task_id 不在内核 tasks 表中。"""


class DenialError(Exception):
    """命令被结构性拒绝（携缺口清单，可离线复现）。"""

    def __init__(self, gaps: VerificationGaps, message: str) -> None:
        super().__init__(message)
        self.gaps = gaps
        self.message = message
