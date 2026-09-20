# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Task 归因切面 wire 契约测试（claims / evidence / verification / gaps）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ghrah.protocol.types import (
    ClaimantType,
    CommandType,
    TaskCheckOutcomePayload,
    TaskClaimEventPayload,
    TaskClaimListPayload,
    TaskClaimListResultPayload,
    TaskClaimPayload,
    TaskEvidenceInput,
    TaskEvidencePayload,
    TaskInfoPayload,
    TaskMissingCheckPayload,
    TaskProvenancePayload,
    TaskStatus,
    TaskSubmitCompletionPayload,
    TaskVerificationGapsPayload,
    TaskVerificationPayload,
    TaskVerifyPayload,
)


def _claim(**overrides: object) -> TaskClaimPayload:
    base: dict[str, object] = {
        "claim_id": "claim-001",
        "task_id": "task-001",
        "claimant_id": "agent-1",
        "state": "submitted",
    }
    base.update(overrides)
    return TaskClaimPayload.model_validate(base)  # type: ignore[arg-type]


class TestClaimWire:
    def test_minimal_claim(self) -> None:
        claim = _claim()
        assert claim.claimant_type == ClaimantType.AGENT
        assert claim.evidence == []
        assert claim.checks == []
        assert claim.provenance is None

    def test_full_claim_roundtrip(self) -> None:
        claim = _claim(
            claimant_name="backend-dev",
            note="login flow implemented",
            evidence=[
                TaskEvidencePayload(
                    evidence_id="ev-001",
                    kind="git_commit",
                    ref="abc1234",
                    payload={"repo": "ghrah", "branch": "main"},
                )
            ],
            state="verified",
            checks=[TaskCheckOutcomePayload(checker="commit_in_repo", passed=True)],
            verdict_by="human:reviewer",
            verdict_reason="lgtm",
            provenance=TaskProvenancePayload(agent_id="a1", node_id="node-001"),
        )
        wire = claim.model_dump(mode="json")
        reparsed = TaskClaimPayload.model_validate(wire)
        assert reparsed == claim
        assert wire["evidence"][0]["kind"] == "git_commit"

    def test_state_literal_boundary(self) -> None:
        for state in ("submitted", "verified", "rejected", "superseded"):
            assert _claim(state=state).state == state
        with pytest.raises(ValidationError):
            _claim(state="open")

    def test_delivered_status_registered(self) -> None:
        assert TaskStatus.DELIVERED.value == "delivered"


class TestEvidenceWire:
    def test_evidence_kind_is_open_string(self) -> None:
        """开放 kind 探针：未知 evidence kind 通过校验（插件可声明新 kind，安全穿透）。"""
        evidence = TaskEvidencePayload(
            evidence_id="ev-001", kind="custom_future_kind", ref="some-ref"
        )
        assert evidence.kind == "custom_future_kind"

    def test_evidence_input_has_no_server_fields(self) -> None:
        raw = TaskEvidenceInput(kind="git_commit", ref="abc1234", digest="sha256:deadbeef")
        wire = raw.model_dump(mode="json")
        assert set(wire) == {"kind", "ref", "digest", "payload"}
        # 仓内惯例 extra=ignore：误传服务端字段被静默丢弃，id/时间戳只由内核分配
        polluted = TaskEvidenceInput.model_validate(
            {**wire, "evidence_id": "ev-001", "created_at": "2026-09-20T00:00:00Z"}
        )
        assert "evidence_id" not in polluted.model_dump(mode="json")


class TestCommands:
    def test_submit_completion_minimal(self) -> None:
        payload = TaskSubmitCompletionPayload(task_id="task-001", claimant_id="agent-1")
        assert payload.claimant_type == ClaimantType.AGENT
        assert payload.evidence == []
        assert payload.expected_version is None

    def test_submit_completion_full(self) -> None:
        payload = TaskSubmitCompletionPayload(
            task_id="task-001",
            claimant_type="human",
            claimant_id="human:dev",
            claimant_name="dev",
            note="done",
            evidence=[{"kind": "git_commit", "ref": "abc1234"}],
            provenance={"session_id": "sess-001", "node_id": "node-001"},
            expected_version=7,
        )
        assert payload.evidence[0].kind == "git_commit"
        assert payload.provenance is not None and payload.provenance.session_id == "sess-001"

    def test_verify_verdict_boundary(self) -> None:
        ok = TaskVerifyPayload(
            task_id="task-001",
            claim_id="claim-001",
            verdict="rejected",
            verifier_id="human:reviewer",
            reason="missing tests",
        )
        assert ok.verdict == "rejected"
        assert (
            TaskVerifyPayload(
                task_id="t", claim_id="c", verdict="verified", verifier_id="v"
            ).verdict
            == "verified"
        )
        with pytest.raises(ValidationError):
            TaskVerifyPayload(task_id="t", claim_id="c", verdict="approved", verifier_id="v")

    def test_list_claims_filters(self) -> None:
        payload = TaskClaimListPayload(task_id="task-001", state="submitted", limit=50)
        assert payload.state == "submitted"
        assert payload.limit == 50
        assert TaskClaimListPayload().task_id is None

    def test_list_claims_result(self) -> None:
        result = TaskClaimListResultPayload(claims=[_claim()], count=1)
        assert result.model_dump(mode="json")["count"] == 1


class TestVerificationAndGaps:
    def test_verification_defaults_empty(self) -> None:
        """空 verification = 无要求，submit 即过保留打勾体验。"""
        empty = TaskVerificationPayload()
        assert empty.evidence_min is None
        assert empty.evidence_kinds == []
        assert empty.checks == []
        assert empty.approver is None

    def test_task_info_verification_optional(self) -> None:
        task = TaskInfoPayload(task_id="t", project_id="p", title="x")
        assert task.verification is None
        task_with_verification = TaskInfoPayload.model_validate(
            {
                "task_id": "t",
                "project_id": "p",
                "title": "x",
                "verification": {"evidence_min": 1, "checks": ["commit_in_repo"]},
            }
        )
        assert task_with_verification.verification is not None
        assert task_with_verification.verification.checks == ["commit_in_repo"]

    def test_gaps_payload_full(self) -> None:
        """缺口清单 wire：Agent 可直接消费的结构化 Denial（含 checker 候选插件）。"""
        gaps = TaskVerificationGapsPayload(
            evidence_have=0,
            evidence_need=1,
            missing_evidence_kinds=["git_commit"],
            missing_checks=[
                TaskMissingCheckPayload(
                    checker="commit_in_repo", candidates=["task-commit-attribution"]
                )
            ],
            failed_checks=[
                TaskCheckOutcomePayload(checker="tests_pass", passed=False, detail="2 failed")
            ],
            missing_approver="human",
        )
        wire = gaps.model_dump(mode="json")
        assert wire["missing_checks"][0]["candidates"] == ["task-commit-attribution"]
        assert wire["failed_checks"][0]["passed"] is False
        assert wire["missing_approver"] == "human"


class TestAttributionEvents:
    def test_claim_event_payload(self) -> None:
        event = TaskClaimEventPayload(
            task=TaskInfoPayload(task_id="task-001", project_id="p", title="x", status="delivered"),
            claim=_claim(),
            previous_status="in_progress",
            reason=None,
        )
        wire = event.model_dump(mode="json")
        assert wire["task"]["status"] == "delivered"
        assert wire["claim"]["claim_id"] == "claim-001"
        assert wire["previous_status"] == "in_progress"

    def test_rejected_event_carries_reason(self) -> None:
        event = TaskClaimEventPayload(
            task=TaskInfoPayload(
                task_id="task-001", project_id="p", title="x", status="in_progress"
            ),
            claim=_claim(state="rejected", verdict_reason="evidence incomplete"),
            previous_status="delivered",
            reason="evidence incomplete",
        )
        assert event.claim.state == "rejected"
        assert event.claim.verdict_reason == "evidence incomplete"

    def test_commands_wired_into_envelope(self) -> None:
        from ghrah.protocol.types import COMMAND_PAYLOAD_MAP

        assert (
            COMMAND_PAYLOAD_MAP[CommandType.TASK_SUBMIT_COMPLETION] is TaskSubmitCompletionPayload
        )
        assert COMMAND_PAYLOAD_MAP[CommandType.TASK_VERIFY] is TaskVerifyPayload
        assert COMMAND_PAYLOAD_MAP[CommandType.TASK_LIST_CLAIMS] is TaskClaimListPayload
