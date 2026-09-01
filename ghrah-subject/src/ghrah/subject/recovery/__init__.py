# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Recovery 模块：Subject 全栈恢复（desired-state 持久化 + reconcile）。

- ``desired_state.DesiredStateRecord`` / ``DesiredStateStore``：单行全量快照，
  desired-state 唯一真相源。
- ``reconciler.ReconciliationService`` / ``ReconcileReport``：start() 末尾 reconcile
  + 首启 bootstrap default project + 事件。
"""

from __future__ import annotations

from ghrah.subject.recovery.desired_state import (
    DesiredStateRecord,
    DesiredStateStore,
    UnitSpec,
)
from ghrah.subject.recovery.reconciler import ReconcileReport, ReconciliationService

__all__ = [
    "DesiredStateRecord",
    "DesiredStateStore",
    "ReconcileReport",
    "ReconciliationService",
    "UnitSpec",
]
