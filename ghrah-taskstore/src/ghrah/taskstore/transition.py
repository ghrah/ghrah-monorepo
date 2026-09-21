# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""纯转移：submit / verify / complete 的 (state, cmd, frozen) → state' | Denial。

零 IO、零钟读、零世界读取——机械校验结果已在 submit 边界冻结为 frozen_checks，
重放不重跑 checker（探针 15 内核半）。Denial 缺口清单稳定排序（探针 14 离线复现）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ghrah.taskstore.models import (
    ClaimRecord,
    ClaimState,
    MissingCheck,
    Outcome,
    TaskStatus,
    Verification,
    VerificationGaps,
)

if TYPE_CHECKING:
    from ghrah.taskstore.models import CheckOutcome, ClaimantType, EvidenceRecord, Provenance

__all__ = [
    "complete_outcome",
    "submit_outcome",
    "verify_outcome",
]

_SUBMIT_ERROR = "verification gaps"
_SELF_APPROVAL_ERROR = "approver must not verify their own claim"
_NOT_SUBMITTED_ERROR = "claim is not in submitted state"
_VERIFICATION_REQUIRED_ERROR = "task requires verification; complete is not allowed"


def _sorted_unique(values: list[str]) -> list[str]:
    """稳定排序 + 去重（缺口清单确定性）。"""

    return sorted(set(values))


def submit_outcome(
    task: ClaimRecord | object,
    verification: Verification | None,
    evidence: list[EvidenceRecord],
    frozen_checks: list[CheckOutcome],
    check_candidates: dict[str, list[str]],
    *,
    claim_id: str,
    claimant_type: ClaimantType,
    claimant_id: str,
    claimant_name: str | None,
    note: str | None,
    provenance: Provenance | None,
    created_at: object,
    has_open_claim: bool,
) -> Outcome:
    """submit_completion 转移：verification 为空 → delivered；否则评估缺口。

    Args:
        task: 当前 task 记录。
        verification: task 的声明式要求（空字段 = 无要求）。
        evidence: submit 附带的证据（已落库快照）。
        frozen_checks: 边界已执行并冻结的 checker 结果。
        check_candidates: checker 未命中时的候选提供插件清单（checker → candidates）。
        claim_id / created_at: 边界分配（本函数零生成）。
        has_open_claim: 是否已有 submitted claim（是则其被 superseded 由调用方落库）。

    Returns:
        Outcome：Ok（data=（新 claim, 新 task 状态)）或 Denial（缺口清单）。
    """

    verification = verification or Verification()
    gaps = VerificationGaps(evidence_have=len(evidence))
    denied = False

    if verification.evidence_min is not None and len(evidence) < verification.evidence_min:
        gaps.evidence_need = verification.evidence_min
        denied = True

    if verification.evidence_kinds:
        have_kinds = _sorted_unique([e.kind for e in evidence])
        wanted = _sorted_unique(verification.evidence_kinds)
        missing_kinds = [k for k in wanted if k not in have_kinds]
        if missing_kinds:
            gaps.missing_evidence_kinds = missing_kinds
            denied = True

    for name in _sorted_unique(verification.checks):
        outcome = next((c for c in frozen_checks if c.checker == name), None)
        if outcome is None:
            # checker 未执行（未命中注册表或构造失败）：记缺失与候选
            gaps.missing_checks.append(
                MissingCheck(checker=name, candidates=list(check_candidates.get(name, ())))
            )
            denied = True
        elif not outcome.passed:
            gaps.failed_checks.append(outcome)
            denied = True

    if verification.approver is not None and verification.approver == claimant_id:
        # 提出者与审批要求同人：submit 仍可过，审批拦截在 verify（执行者独立原则）
        pass

    if denied:
        return Outcome.denied(gaps, _SUBMIT_ERROR)

    new_task_status = TaskStatus.DELIVERED
    new_claim = ClaimRecord(
        claim_id=claim_id,
        task_id=task.task_id,  # type: ignore[attr-defined]
        claimant_type=claimant_type,
        claimant_id=claimant_id,
        claimant_name=claimant_name,
        note=note,
        evidence_ids=[e.evidence_id for e in evidence],
        state=ClaimState.SUBMITTED,
        checks=list(frozen_checks),
        provenance=provenance,
        created_at=created_at,  # type: ignore[arg-type]
    )
    return Outcome.ok(
        {"task_status": new_task_status, "claim": new_claim, "superseded": has_open_claim}
    )


def verify_outcome(
    task: object,
    claim: ClaimRecord,
    verification: Verification | None,
    *,
    verdict: str,
    verifier_id: str,
    reason: str | None,
    verified_at: object,
) -> Outcome:
    """verify 转移：submitted claim 的验收裁决。

    执行者独立原则：approver 非空时 verifier_id != claimant_id 强制。
    verified → task completed；rejected → task in_progress + claim rejected。
    """

    if claim.state is not ClaimState.SUBMITTED:
        return Outcome.denied(VerificationGaps(), f"{_NOT_SUBMITTED_ERROR}: {claim.state.value}")

    verification = verification or Verification()
    if verification.approver is not None and verifier_id == claim.claimant_id:
        return Outcome.denied(VerificationGaps(), _SELF_APPROVAL_ERROR)

    from ghrah.taskstore.models import Verdict

    verdict_value = Verdict(verdict)
    new_task_status = (
        TaskStatus.COMPLETED if verdict_value is Verdict.VERIFIED else TaskStatus.IN_PROGRESS
    )
    new_claim_state = (
        ClaimState.VERIFIED if verdict_value is Verdict.VERIFIED else ClaimState.REJECTED
    )
    new_claim = claim.model_copy(
        update={
            "state": new_claim_state,
            "verdict_by": verifier_id,
            "verdict_at": verified_at,  # type: ignore[arg-type]
            "verdict_reason": reason,
        }
    )
    return Outcome.ok({"task_status": new_task_status, "claim": new_claim})


def complete_outcome(
    task: object,
    verification: Verification | None,
) -> Outcome:
    """complete 快捷通道：verification 非空 → Denial（必须走 submit/verify）。"""

    if verification is not None and verification != Verification():
        return Outcome.denied(VerificationGaps(), _VERIFICATION_REQUIRED_ERROR)
    return Outcome.ok({"task_status": TaskStatus.COMPLETED})
