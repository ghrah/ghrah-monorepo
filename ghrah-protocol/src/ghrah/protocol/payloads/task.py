# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""Task 域载荷模型（命令与事件，含完成归因切面：claims/evidence/verification）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ghrah.protocol.enums import ClaimantType, TaskPriority, TaskStatus

# ─── Task 命令和事件载荷模型 ───


class TaskVerificationPayload(BaseModel):
    """verification 声明式要求对象（空字段 = 无要求，submit 即过保留打勾体验）。

    Attributes:
        evidence_min: 最少证据条数。
        evidence_kinds: 证据类型白名单（开放字符串，插件可声明新 kind）。
        checks: 机械校验器注册表名清单（开放字符串）。
        approver: 审批要求（"human"=HITL 他人审批 | 具体 agent_id | None=无需人工）。
    """

    evidence_min: int | None = None
    evidence_kinds: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    approver: str | None = None


class TaskInfoPayload(BaseModel):
    """Task 信息载荷，用于 task 命令结果和事件。"""

    task_id: str
    project_id: str
    title: str
    description: str = ""
    agent_id: str | None = None
    agent_name: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    parent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    verification: TaskVerificationPayload | None = None


class TaskCreatePayload(BaseModel):
    """task_create 命令载荷。"""

    title: str
    project_id: str
    description: str = ""
    agent_id: str | None = None
    agent_name: str | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    parent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdatePayload(BaseModel):
    """task_update 命令载荷。"""

    task_id: str
    title: str | None = None
    description: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    parent_id: str | None = None
    dependencies: list[str] | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    metadata_patch: dict[str, Any] | None = None
    expected_version: int | None = None


class TaskIdPayload(BaseModel):
    """task_* 单任务命令载荷。"""

    task_id: str


class TaskAssignPayload(TaskIdPayload):
    """task_assign 命令载荷。"""

    agent_id: str = ""
    agent_name: str


class TaskCompletePayload(TaskIdPayload):
    """task_complete 命令载荷。"""

    result: Any = None


class TaskFailPayload(TaskIdPayload):
    """task_fail 命令载荷。"""

    error: str


class TaskCancelPayload(TaskIdPayload):
    """task_cancel 命令载荷。"""

    reason: str | None = None


class TaskBlockPayload(TaskIdPayload):
    """task_block 命令载荷。"""

    reason: str | None = None


class TaskListPayload(BaseModel):
    """task_list 命令载荷。"""

    agent_id: str | None = None
    agent_name: str | None = None
    status: TaskStatus | list[TaskStatus] | None = None
    parent_id: str | None = None
    project_id: str | None = None
    include_terminal: bool = True
    limit: int = 100


class TaskDeletePayload(TaskIdPayload):
    """task_delete 命令载荷。"""

    force: bool = False


class TaskListResultPayload(BaseModel):
    """task_list 命令响应载荷。"""

    tasks: list[TaskInfoPayload] = Field(default_factory=list)
    count: int = 0


class TaskEventPayload(BaseModel):
    """task_* 事件载荷。"""

    task: TaskInfoPayload
    previous_status: TaskStatus | None = None
    reason: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None


# ─── Task 归因切面：claims / evidence / verification gaps ───
#
# 归因链：task ─ claim(谁认领) ─ evidence[](凭什么) ─ verdict(谁判的)，
# provenance 把声明锚定到产生它的 ActionChain 轨迹节点。
# evidence.kind 与 checker 名是开放字符串（插件可声明新 evidence_kinds），
# wire 不做闭合枚举——未知类型两侧安全穿透不崩溃。


class TaskEvidenceInput(BaseModel):
    """submit_completion 提交的证据输入（id/时间戳由服务端分配）。"""

    kind: str
    ref: str
    digest: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskEvidencePayload(BaseModel):
    """证据记录载荷（evidence 表投影）。"""

    evidence_id: str
    kind: str
    ref: str
    digest: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    created_at: str = ""


class TaskCheckOutcomePayload(BaseModel):
    """冻结的机械校验结果（submit 边界执行后冻结记录入 claim，重放不重跑）。"""

    checker: str
    passed: bool
    detail: str | None = None


class TaskProvenancePayload(BaseModel):
    """证据声明来源锚点（Subject 面注入：agent/session/branch/node）。"""

    agent_id: str | None = None
    session_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None


class TaskClaimPayload(BaseModel):
    """claim（完成声明）载荷，归因的核心载体。"""

    claim_id: str
    task_id: str
    claimant_type: ClaimantType = ClaimantType.AGENT
    claimant_id: str
    claimant_name: str | None = None
    note: str | None = None
    evidence: list[TaskEvidencePayload] = Field(default_factory=list)
    state: Literal["submitted", "verified", "rejected", "superseded"]
    checks: list[TaskCheckOutcomePayload] = Field(default_factory=list)
    verdict_by: str | None = None
    verdict_at: str | None = None
    verdict_reason: str | None = None
    provenance: TaskProvenancePayload | None = None
    created_at: str = ""


class TaskSubmitCompletionPayload(BaseModel):
    """task_submit_completion 命令载荷（建 claim → 交付评估）。"""

    task_id: str
    claimant_type: ClaimantType = ClaimantType.AGENT
    claimant_id: str
    claimant_name: str | None = None
    note: str | None = None
    evidence: list[TaskEvidenceInput] = Field(default_factory=list)
    provenance: TaskProvenancePayload | None = None
    expected_version: int | None = None


class TaskVerifyPayload(BaseModel):
    """task_verify 命令载荷（verdict → completed / 打回 in_progress）。"""

    task_id: str
    claim_id: str
    verdict: Literal["verified", "rejected"]
    verifier_id: str
    verifier_name: str | None = None
    reason: str | None = None
    expected_version: int | None = None


class TaskClaimListPayload(BaseModel):
    """task_list_claims 查询载荷。"""

    task_id: str | None = None
    claimant_id: str | None = None
    state: (
        Literal["submitted", "verified", "rejected", "superseded"]
        | list[Literal["submitted", "verified", "rejected", "superseded"]]
        | None
    ) = None
    limit: int = 100


class TaskClaimListResultPayload(BaseModel):
    """task_list_claims 查询响应载荷（command_result.data）。"""

    claims: list[TaskClaimPayload] = Field(default_factory=list)
    count: int = 0


class TaskClaimEventPayload(BaseModel):
    """task_delivered / task_verified / task_rejected 事件载荷（task 附 claim）。"""

    task: TaskInfoPayload
    claim: TaskClaimPayload
    previous_status: TaskStatus | None = None
    reason: str | None = None


class TaskMissingCheckPayload(BaseModel):
    """缺口清单条目：缺失 checker 及其候选提供插件。"""

    checker: str
    candidates: list[str] = Field(default_factory=list)


class TaskVerificationGapsPayload(BaseModel):
    """submit_completion 被拒时的缺口清单（Agent 可直接消费的结构化 Denial）。"""

    evidence_have: int = 0
    evidence_need: int | None = None
    missing_evidence_kinds: list[str] = Field(default_factory=list)
    missing_checks: list[TaskMissingCheckPayload] = Field(default_factory=list)
    failed_checks: list[TaskCheckOutcomePayload] = Field(default_factory=list)
    missing_approver: str | None = None


class TaskDumpPayload(BaseModel):
    """task_dump 查询载荷（归因链全量快照重建入口）。"""

    project_id: str | None = None
    include_deleted: bool = False
    limit: int | None = None


class TaskDumpResultPayload(BaseModel):
    """task_dump 查询响应载荷（command_result.data）。

    limit 仅限制 tasks 条数；claims 仅含所选 tasks 的 claim，evidence 仅含
    这些 claim 的 evidence_ids 关联记录（给定 tasks 集合可完整重建归因链）。
    claims 内嵌 evidence 与 evidence 列表并存：供单命令重建与表级保真两种消费。
    """

    tasks: list[TaskInfoPayload] = Field(default_factory=list)
    claims: list[TaskClaimPayload] = Field(default_factory=list)
    evidence: list[TaskEvidencePayload] = Field(default_factory=list)
