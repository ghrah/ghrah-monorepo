# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""任务归因内核（taskstore）。

tasks / claims / evidence 三表的唯一权威（SSOT）；命令/查询 facade 与确定性
转移分离（边界 impure / 转移 pure）；checker 扩展点宿主（S1 wire 的内核半）。

零 ghrah 域包依赖：仅 aiosqlite / pydantic / ghrah-plugin（L2 基础设施）。
wire 映射归 ghrah-subject 的 TaskStoreUnit，本包不感知协议。
"""

from ghrah.taskstore.checkers import (
    Checker,
    CheckerRegistry,
    CheckOutcome,
    freeze_mapping,
)
from ghrah.taskstore.errors import (
    ConcurrentModificationError,
    DenialError,
    TaskNotFoundError,
)
from ghrah.taskstore.kernel import (
    Clock,
    IdFactory,
    KernelEvent,
    OnEvent,
    PluginRegistryProvider,
    TaskStoreKernel,
)
from ghrah.taskstore.models import (
    ClaimantType,
    ClaimRecord,
    ClaimState,
    EvidenceRecord,
    Outcome,
    Provenance,
    TaskRecord,
    TaskStatus,
    Verdict,
    Verification,
    VerificationGaps,
)
from ghrah.taskstore.store import TaskStore

__all__ = [
    "Checker",
    "CheckerRegistry",
    "CheckOutcome",
    "Clock",
    "ClaimRecord",
    "ClaimState",
    "ClaimantType",
    "ConcurrentModificationError",
    "DenialError",
    "EvidenceRecord",
    "IdFactory",
    "KernelEvent",
    "OnEvent",
    "Outcome",
    "PluginRegistryProvider",
    "Provenance",
    "TaskNotFoundError",
    "TaskRecord",
    "TaskStatus",
    "TaskStore",
    "TaskStoreKernel",
    "Verification",
    "VerificationGaps",
    "Verdict",
    "freeze_mapping",
]
