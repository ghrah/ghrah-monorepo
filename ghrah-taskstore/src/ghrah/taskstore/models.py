# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""内核域模型：task / claim / evidence 与 verification 缺口清单。

独立于协议包（零 ghrah 域包依赖），字段与 S1 wire 载荷对齐（TaskInfoPayload /
TaskClaimPayload / TaskVerificationGapsPayload），由 Subject 适配层做映射。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ClaimRecord",
    "ClaimState",
    "ClaimantType",
    "CheckOutcome",
    "EvidenceRecord",
    "Outcome",
    "Provenance",
    "TASK_STATUS_VALUES",
    "TaskRecord",
    "TaskStatus",
    "TRANSITIONS",
    "Verification",
    "VerificationGaps",
    "Verdict",
    "can_transition",
]

# ─── 状态机（上游 §4.3：completed 仅经 verify / complete；delivered 仅经 submit）───


class TaskStatus(StrEnum):
    """Task 生命周期状态（含归因中间态 delivered）。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ClaimState(StrEnum):
    """Claim（完成声明）状态。"""

    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ClaimantType(StrEnum):
    """Claim 提出者类型。"""

    AGENT = "agent"
    HUMAN = "human"


class Verdict(StrEnum):
    """验收裁决。"""

    VERIFIED = "verified"
    REJECTED = "rejected"


TASK_STATUS_VALUES: frozenset[str] = frozenset(status.value for status in TaskStatus)

TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.CANCELED}
    ),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELED}),
    TaskStatus.BLOCKED: frozenset(
        {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.FAILED, TaskStatus.CANCELED}
    ),
    TaskStatus.DELIVERED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED}),
    # completed 仅经 verify（delivered → completed）或 complete（非 delivered 直通，
    # 见 transition.complete_outcome：verification 为空时 pending/in_progress → completed）
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELED: frozenset(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """判断状态机是否允许 current → target（verify/complete 的直通通道在转移函数内判）。"""

    return target in TRANSITIONS.get(current, frozenset())


# ─── verification 声明式要求（空字段 = 无要求，submit 即过保留打勾体验）───


class Verification(BaseModel):
    """verification 声明式要求对象。"""

    model_config = ConfigDict(extra="forbid")

    evidence_min: int | None = None
    evidence_kinds: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    approver: str | None = None


# ─── 证据 / 校验结果 / 来源锚点 ───


class EvidenceRecord(BaseModel):
    """证据记录（evidence 表行；kind 为开放字符串，插件可声明新 kind）。"""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    kind: str
    ref: str
    digest: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    created_at: datetime


class CheckOutcome(BaseModel):
    """冻结的机械校验结果（submit 边界执行后冻结入 claim，重放不重跑）。"""

    model_config = ConfigDict(extra="forbid")

    checker: str
    passed: bool
    detail: str | None = None


class Provenance(BaseModel):
    """证据声明来源锚点（Subject 面注入：agent/session/branch/node）。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: str | None = None
    session_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None


# ─── task / claim 记录 ───


class TaskRecord(BaseModel):
    """内核 task 记录（tasks 表行）。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    project_id: str
    seq: int
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    acceptance: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    verification: Verification | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ClaimRecord(BaseModel):
    """内核 claim 记录（claims 表行，归因的核心载体）。"""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    task_id: str
    claimant_type: ClaimantType = ClaimantType.AGENT
    claimant_id: str
    claimant_name: str | None = None
    note: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    state: ClaimState = ClaimState.SUBMITTED
    checks: list[CheckOutcome] = Field(default_factory=list)
    verdict_by: str | None = None
    verdict_at: datetime | None = None
    verdict_reason: str | None = None
    provenance: Provenance | None = None
    version: int = 1
    created_at: datetime


# ─── Denial 缺口清单（字段对齐 S1 TaskVerificationGapsPayload）───


class MissingCheck(BaseModel):
    """缺口清单条目：缺失 checker 及其候选提供插件。"""

    model_config = ConfigDict(extra="forbid")

    checker: str
    candidates: list[str] = Field(default_factory=list)


class VerificationGaps(BaseModel):
    """submit_completion 被拒时的缺口清单（结构化 Denial，可离线复现）。"""

    model_config = ConfigDict(extra="forbid")

    evidence_have: int = 0
    evidence_need: int | None = None
    missing_evidence_kinds: list[str] = Field(default_factory=list)
    missing_checks: list[MissingCheck] = Field(default_factory=list)
    failed_checks: list[CheckOutcome] = Field(default_factory=list)
    missing_approver: str | None = None


# ─── 统一 Outcome ───


class Outcome(BaseModel):
    """内核 facade 统一返回：Ok 或 Denial（携缺口清单）。"""

    model_config = ConfigDict(extra="forbid")

    success: bool
    data: Any = None
    error: str | None = None
    denial: VerificationGaps | None = None

    @classmethod
    def ok(cls, data: Any = None) -> Outcome:
        """构造 Ok 结果。"""

        return cls(success=True, data=data)

    @classmethod
    def denied(cls, gaps: VerificationGaps, error: str) -> Outcome:
        """构造 Denial 结果（error 为人读摘要）。"""

        return cls(success=False, error=error, denial=gaps)
