# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""models 测试：状态机边界、gaps 默认值、evidence kind 开放字符串（探针 10 内核半）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ghrah.taskstore.models import (
    ClaimState,
    EvidenceRecord,
    Outcome,
    TaskRecord,
    TaskStatus,
    Verification,
    VerificationGaps,
    can_transition,
)


def _task(status: TaskStatus = TaskStatus.PENDING) -> TaskRecord:
    now = datetime(2026, 9, 21, tzinfo=UTC)
    return TaskRecord(
        task_id="t1",
        project_id="p1",
        seq=1,
        title="demo",
        status=status,
        created_at=now,
        updated_at=now,
    )


class TestStateMachine:
    def test_delivered_only_via_submit_channel(self):
        """delivered 不在任何 update_task 可达集合（只能经 submit）。"""
        for status in TaskStatus:
            assert not can_transition(status, TaskStatus.DELIVERED)

    def test_completed_only_from_delivered(self):
        """completed 仅从 delivered 可达（verify 通道；complete 直通不走本表）。"""
        for status in TaskStatus:
            if status is TaskStatus.DELIVERED:
                assert can_transition(status, TaskStatus.COMPLETED)
            else:
                assert not can_transition(status, TaskStatus.COMPLETED)

    def test_delivered_can_go_back_or_completed(self):
        """delivered → in_progress（打回）/ completed（验收通过）合法。"""
        assert can_transition(TaskStatus.DELIVERED, TaskStatus.IN_PROGRESS)
        assert can_transition(TaskStatus.DELIVERED, TaskStatus.COMPLETED)

    def test_terminal_states_frozen(self):
        for status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED):
            for target in TaskStatus:
                assert not can_transition(status, target)


class TestModels:
    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            TaskRecord(
                task_id="t",
                project_id="p",
                seq=1,
                title="x",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                unknown_field=1,
            )

    def test_verification_defaults_empty(self):
        """空字段 = 无要求（submit 即过保留打勾体验）。"""
        v = Verification()
        assert v.evidence_min is None
        assert v.evidence_kinds == []
        assert v.checks == []
        assert v.approver is None

    def test_gaps_defaults(self):
        gaps = VerificationGaps()
        assert gaps.evidence_have == 0
        assert gaps.evidence_need is None
        assert gaps.missing_evidence_kinds == []
        assert gaps.missing_checks == []
        assert gaps.failed_checks == []
        assert gaps.missing_approver is None

    def test_unknown_evidence_kind_open_string(self):
        """探针 10：未知 evidence kind 为开放字符串，校验通过。"""
        ev = EvidenceRecord(
            evidence_id="e1",
            kind="exotic-future-kind",
            ref="whatever",
            digest=None,
            created_at=datetime(2026, 9, 21, tzinfo=UTC),
        )
        assert ev.kind == "exotic-future-kind"

    def test_claim_state_values(self):
        assert {s.value for s in ClaimState} == {"submitted", "verified", "rejected", "superseded"}

    def test_task_default_status_pending(self):
        assert _task().status is TaskStatus.PENDING

    def test_outcome_helpers(self):
        ok = Outcome.ok({"a": 1})
        assert ok.success and ok.data == {"a": 1} and ok.denial is None
        gaps = VerificationGaps(evidence_have=0, evidence_need=2)
        denial = Outcome.denied(gaps, "缺口")
        assert not denial.success
        assert denial.denial is gaps
        assert denial.error == "缺口"
