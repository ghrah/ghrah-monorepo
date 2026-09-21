# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""transition 测试：三命令全分支 + 不变量 + 同输入同 Denial（离线复现）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghrah.taskstore.models import (
    CheckOutcome,
    ClaimRecord,
    ClaimState,
    EvidenceRecord,
    TaskRecord,
    TaskStatus,
    Verification,
)
from ghrah.taskstore.transition import complete_outcome, submit_outcome, verify_outcome

NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


def _task(verification: Verification | None = None) -> TaskRecord:
    return TaskRecord(
        task_id="t1",
        project_id="p1",
        seq=1,
        title="demo",
        status=TaskStatus.IN_PROGRESS,
        verification=verification,
        created_at=NOW,
        updated_at=NOW,
    )


def _claim(claimant_id: str = "agent-1") -> ClaimRecord:
    return ClaimRecord(
        claim_id="c1",
        task_id="t1",
        claimant_id=claimant_id,
        state=ClaimState.SUBMITTED,
        created_at=NOW,
    )


def _evidence(evidence_id: str = "e1", kind: str = "git_commit") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind=kind,
        ref="commit-abc",
        created_by="agent-1",
        created_at=NOW,
    )


class TestSubmit:
    def test_no_verification_submits_directly(self):
        """空字段 = 无要求：submit 即过保留打勾体验。"""
        task = _task(verification=None)
        outcome = submit_outcome(
            task,
            None,
            evidence=[],
            frozen_checks=[],
            check_candidates={},
            claim_id="c-new",
            claimant_type="agent",
            claimant_id="agent-1",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        assert outcome.success
        assert outcome.data["task_status"] is TaskStatus.DELIVERED
        claim = outcome.data["claim"]
        assert claim.state is ClaimState.SUBMITTED
        assert claim.claim_id == "c-new"

    def test_empty_verification_object_also_passes(self):
        task = _task(verification=Verification())
        outcome = submit_outcome(
            task,
            Verification(),
            evidence=[],
            frozen_checks=[],
            check_candidates={},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        assert outcome.success

    def test_evidence_min_gap(self):
        task = _task(verification=Verification(evidence_min=2))
        outcome = submit_outcome(
            task,
            task.verification,
            evidence=[_evidence()],
            frozen_checks=[],
            check_candidates={},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        assert not outcome.success
        gaps = outcome.denial
        assert gaps is not None
        assert gaps.evidence_have == 1
        assert gaps.evidence_need == 2

    def test_missing_evidence_kinds(self):
        verification = Verification(evidence_kinds=["git_commit", "screenshot"])
        task = _task(verification=verification)
        outcome = submit_outcome(
            task,
            verification,
            evidence=[_evidence(kind="git_commit")],
            frozen_checks=[],
            check_candidates={},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        assert not outcome.success
        assert outcome.denial is not None
        assert outcome.denial.missing_evidence_kinds == ["screenshot"]

    def test_missing_check_with_candidates(self):
        verification = Verification(checks=["commit_in_repo", "lint_clean"])
        task = _task(verification=verification)
        frozen = [CheckOutcome(checker="lint_clean", passed=True)]
        outcome = submit_outcome(
            task,
            verification,
            evidence=[_evidence()],
            frozen_checks=frozen,
            check_candidates={"commit_in_repo": ["plugin-a", "plugin-b"]},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        assert not outcome.success
        gaps = outcome.denial
        assert gaps is not None
        assert len(gaps.missing_checks) == 1
        assert gaps.missing_checks[0].checker == "commit_in_repo"
        assert gaps.missing_checks[0].candidates == ["plugin-a", "plugin-b"]

    def test_failed_check_recorded(self):
        verification = Verification(checks=["commit_in_repo"])
        task = _task(verification=verification)
        frozen = [CheckOutcome(checker="commit_in_repo", passed=False, detail="not in repo")]
        outcome = submit_outcome(
            task,
            verification,
            evidence=[_evidence()],
            frozen_checks=frozen,
            check_candidates={},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        assert not outcome.success
        gaps = outcome.denial
        assert gaps is not None
        assert gaps.failed_checks == frozen

    def test_all_pass_delivers_with_frozen_checks_in_claim(self):
        verification = Verification(evidence_min=1, checks=["commit_in_repo"])
        task = _task(verification=verification)
        frozen = [CheckOutcome(checker="commit_in_repo", passed=True)]
        outcome = submit_outcome(
            task,
            verification,
            evidence=[_evidence("e1")],
            frozen_checks=frozen,
            check_candidates={},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=True,
        )
        assert outcome.success
        claim = outcome.data["claim"]
        assert claim.checks == frozen
        assert claim.evidence_ids == ["e1"]
        assert outcome.data["superseded"] is True

    def test_same_input_same_denial(self):
        """同输入两次调用 Denial 逐位一致（离线复现，探针 14 转移半）。"""
        verification = Verification(evidence_min=2, evidence_kinds=["screenshot"], checks=["x"])
        task = _task(verification=verification)
        kwargs = dict(
            evidence=[_evidence()],
            frozen_checks=[],
            check_candidates={"x": ["p"]},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        d1 = submit_outcome(task, verification, **kwargs)
        d2 = submit_outcome(task, verification, **kwargs)
        assert d1.model_dump() == d2.model_dump()
        assert not d1.success

    def test_gap_lists_sorted(self):
        verification = Verification(checks=["z-check", "a-check"])
        task = _task(verification=verification)
        outcome = submit_outcome(
            task,
            verification,
            evidence=[],
            frozen_checks=[],
            check_candidates={},
            claim_id="c",
            claimant_type="agent",
            claimant_id="a",
            claimant_name=None,
            note=None,
            provenance=None,
            created_at=NOW,
            has_open_claim=False,
        )
        assert outcome.denial is not None
        assert [m.checker for m in outcome.denial.missing_checks] == ["a-check", "z-check"]


class TestVerify:
    def test_verified_completes_task(self):
        task = _task()
        claim = _claim()
        outcome = verify_outcome(
            task,
            claim,
            None,
            verdict="verified",
            verifier_id="agent-2",
            reason=None,
            verified_at=NOW,
        )
        assert outcome.success
        assert outcome.data["task_status"] is TaskStatus.COMPLETED
        new_claim = outcome.data["claim"]
        assert new_claim.state is ClaimState.VERIFIED
        assert new_claim.verdict_by == "agent-2"
        assert new_claim.verdict_at == NOW

    def test_rejected_returns_in_progress(self):
        task = _task()
        claim = _claim()
        outcome = verify_outcome(
            task,
            claim,
            None,
            verdict="rejected",
            verifier_id="agent-2",
            reason="证据不足",
            verified_at=NOW,
        )
        assert outcome.success
        assert outcome.data["task_status"] is TaskStatus.IN_PROGRESS
        assert outcome.data["claim"].state is ClaimState.REJECTED
        assert outcome.data["claim"].verdict_reason == "证据不足"

    def test_self_approval_denied(self):
        """探针 2：approver 非空时 claimant 自批拒。"""
        verification = Verification(approver="human")
        task = _task(verification=verification)
        claim = _claim(claimant_id="agent-1")
        outcome = verify_outcome(
            task,
            claim,
            verification,
            verdict="verified",
            verifier_id="agent-1",
            reason=None,
            verified_at=NOW,
        )
        assert not outcome.success
        assert outcome.denial is not None

    def test_self_approval_allowed_when_no_approver(self):
        task = _task()
        claim = _claim(claimant_id="agent-1")
        outcome = verify_outcome(
            task,
            claim,
            None,
            verdict="verified",
            verifier_id="agent-1",
            reason=None,
            verified_at=NOW,
        )
        assert outcome.success

    def test_non_submitted_claim_denied(self):
        claim = _claim().model_copy(update={"state": ClaimState.VERIFIED})
        outcome = verify_outcome(
            _task(),
            claim,
            None,
            verdict="verified",
            verifier_id="agent-2",
            reason=None,
            verified_at=NOW,
        )
        assert not outcome.success

    def test_invalid_verdict_rejected_by_model(self):
        with pytest.raises(ValueError):
            verify_outcome(
                _task(),
                _claim(),
                None,
                verdict="bogus",
                verifier_id="x",
                reason=None,
                verified_at=NOW,
            )


class TestComplete:
    def test_complete_without_verification(self):
        task = _task(verification=None)
        outcome = complete_outcome(task, None)
        assert outcome.success
        assert outcome.data["task_status"] is TaskStatus.COMPLETED

    def test_complete_with_verification_denied(self):
        """探针 2：verification 非空时 complete 直通拒。"""
        verification = Verification(evidence_min=1)
        task = _task(verification=verification)
        outcome = complete_outcome(task, verification)
        assert not outcome.success
        assert outcome.denial is not None

    def test_complete_with_empty_verification_passes(self):
        task = _task(verification=Verification())
        outcome = complete_outcome(task, Verification())
        assert outcome.success
