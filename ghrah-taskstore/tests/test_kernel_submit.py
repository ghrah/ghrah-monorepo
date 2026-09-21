# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""kernel submit 测试：验收①（无证据 Denial 缺口完整）+ 验收②（checker 命中/未命中）。

probe 1/2 切面、probe 10 穿透（未知 evidence kind）、A16 冻结。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from ghrah.taskstore.checkers import CheckerRegistry, CheckOutcome
from ghrah.taskstore.kernel import TaskStoreKernel
from ghrah.taskstore.models import ClaimState, TaskStatus, Verification
from ghrah.taskstore.store import TaskStore

NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self) -> None:
        self.ticks = 0

    def __call__(self) -> datetime:
        self.ticks += 1
        return datetime(2026, 9, 21, 12, 0, self.ticks, tzinfo=UTC)


class CounterIds:
    def __init__(self, prefix: str = "id") -> None:
        self.n = 0
        self.prefix = prefix

    def __call__(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n}"


def _commit_checker(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
    kinds = [e.get("kind") for e in evidence["items"]]
    passed = "git_commit" in kinds
    return {"passed": passed, "detail": None if passed else "no git_commit evidence"}


def _failing_checker(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
    return {"passed": False, "detail": "always fails"}


@pytest.fixture
async def kernel(tmp_path):
    store = TaskStore(tmp_path / "k.sqlite3")
    await store.start()
    registry = CheckerRegistry()
    k = TaskStoreKernel(
        store,
        registry,
        clock=FixedClock(),
        id_factory=CounterIds(),
    )
    yield k
    await store.stop()


async def _make_task(kernel, verification: Verification | None = None, **kwargs):
    return await kernel.create_task(
        project_id=kwargs.pop("project_id", "p1"),
        title="demo",
        verification=verification,
        **kwargs,
    )


class TestSubmitDenial:
    async def test_no_evidence_full_gap_list(self, kernel):
        """验收①：verification 非空时无证据 submit 被 Denial 且缺口清单完整。"""
        verification = Verification(
            evidence_min=1, evidence_kinds=["git_commit"], checks=["commit_in_repo"]
        )
        task = await _make_task(kernel, verification)
        outcome = await kernel.submit_completion(
            task_id=task.task_id, claimant_id="agent-1", evidence=[]
        )
        assert not outcome.success
        gaps = outcome.denial
        assert gaps is not None
        assert gaps.evidence_have == 0
        assert gaps.evidence_need == 1
        assert gaps.missing_evidence_kinds == ["git_commit"]
        assert [m.checker for m in gaps.missing_checks] == ["commit_in_repo"]
        assert gaps.missing_checks[0].candidates == []
        assert gaps.failed_checks == []
        # task 状态未被污染
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.PENDING
        # 无 claim 落库
        assert await kernel.list_claims(task_id=task.task_id) == []

    async def test_checker_miss_records_candidates(self, kernel):
        """验收②（未命中半）：checker 未注册 → missing_checks 含候选（无插件注册表 → 空候选）。"""
        verification = Verification(checks=["commit_in_repo"], evidence_min=1)
        task = await _make_task(kernel, verification)
        outcome = await kernel.submit_completion(
            task_id=task.task_id,
            claimant_id="agent-1",
            evidence=[{"kind": "git_commit", "ref": "abc"}],
        )
        assert not outcome.success
        gaps = outcome.denial
        assert gaps is not None
        assert gaps.evidence_need is None  # evidence_min 已满足
        assert gaps.missing_evidence_kinds == []
        assert len(gaps.missing_checks) == 1
        assert gaps.missing_checks[0].checker == "commit_in_repo"
        assert gaps.missing_checks[0].candidates == []


class TestSubmitChecker:
    async def test_checker_hit_passes_and_freezes(self, kernel):
        """验收②（命中半）：注册 checker → submit 通过，checks 冻结入 claim。"""
        kernel._checkers.register("commit_in_repo", _commit_checker)
        verification = Verification(checks=["commit_in_repo"], evidence_min=1)
        task = await _make_task(kernel, verification)
        outcome = await kernel.submit_completion(
            task_id=task.task_id,
            claimant_id="agent-1",
            evidence=[{"kind": "git_commit", "ref": "abc"}],
        )
        assert outcome.success, outcome.error
        claim = outcome.data["claim"]
        assert claim.checks == [CheckOutcome(checker="commit_in_repo", passed=True, detail=None)]
        assert claim.state is ClaimState.SUBMITTED
        # task → delivered
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.DELIVERED

    async def test_checker_failed_blocks_submit(self, kernel):
        kernel._checkers.register("commit_in_repo", _failing_checker)
        verification = Verification(checks=["commit_in_repo"], evidence_min=1)
        task = await _make_task(kernel, verification)
        outcome = await kernel.submit_completion(
            task_id=task.task_id,
            claimant_id="agent-1",
            evidence=[{"kind": "git_commit", "ref": "abc"}],
        )
        assert not outcome.success
        gaps = outcome.denial
        assert gaps is not None
        assert len(gaps.failed_checks) == 1
        assert gaps.failed_checks[0].checker == "commit_in_repo"

    async def test_evidence_upsert_reused_across_claims(self, kernel):
        verification = Verification(evidence_min=1)
        task = await _make_task(kernel, verification)
        evidence = [{"kind": "git_commit", "ref": "abc", "digest": "d1"}]
        o1 = await kernel.submit_completion(
            task_id=task.task_id, claimant_id="a1", evidence=evidence
        )
        o2 = await kernel.submit_completion(
            task_id=task.task_id, claimant_id="a2", evidence=evidence
        )
        assert o1.success and o2.success
        c1: Any = o1.data["claim"]
        c2: Any = o2.data["claim"]
        assert c1.evidence_ids == c2.evidence_ids  # 同 (kind,ref,digest) 复用
        # 第一条 claim 被 superseded
        claims = await kernel.list_claims(task_id=task.task_id)
        assert {c.state for c in claims} == {ClaimState.SUPERSEDED, ClaimState.SUBMITTED}

    async def test_unknown_evidence_kind_passes_through(self, kernel):
        """探针 10：未知 evidence kind 开放字符串穿透。"""
        verification = Verification(evidence_min=1)
        task = await _make_task(kernel, verification)
        outcome = await kernel.submit_completion(
            task_id=task.task_id,
            claimant_id="agent-1",
            evidence=[{"kind": "exotic-future-kind", "ref": "x"}],
        )
        assert outcome.success

    async def test_no_verification_submits_with_empty_evidence(self, kernel):
        task = await _make_task(kernel, None)
        outcome = await kernel.submit_completion(task_id=task.task_id, claimant_id="a1")
        assert outcome.success
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.DELIVERED

    async def test_events_emitted_on_submit(self, kernel):
        events: list[tuple] = []

        async def on_event(event: tuple) -> None:
            events.append(event)

        kernel._on_event = on_event
        task = await _make_task(kernel, None)
        await kernel.submit_completion(task_id=task.task_id, claimant_id="a1")
        assert len(events) == 1
        event_type, etask, eclaim, prev, _ = events[0]
        assert event_type == "task_delivered"
        assert prev is TaskStatus.PENDING
        assert eclaim.claimant_id == "a1"
