# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""kernel verify / complete 测试：探针 2（自批拒、complete 直通拒）+ 事件。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghrah.taskstore.checkers import CheckerRegistry
from ghrah.taskstore.kernel import TaskStoreKernel
from ghrah.taskstore.models import ClaimState, TaskStatus, Verification
from ghrah.taskstore.store import TaskStore


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


@pytest.fixture
async def kernel(tmp_path):
    store = TaskStore(tmp_path / "k.sqlite3")
    await store.start()
    k = TaskStoreKernel(store, CheckerRegistry(), clock=FixedClock(), id_factory=CounterIds())
    yield k
    await store.stop()


async def _delivered(kernel, verification: Verification | None = None, claimant: str = "agent-1"):
    task = await kernel.create_task(project_id="p1", title="demo", verification=verification)
    outcome = await kernel.submit_completion(task_id=task.task_id, claimant_id=claimant)
    assert outcome.success
    return task, outcome.data["claim"]


class TestVerify:
    async def test_verified_completes(self, kernel):
        task, claim = await _delivered(kernel)
        outcome = await kernel.verify(
            task_id=task.task_id,
            claim_id=claim.claim_id,
            verdict="verified",
            verifier_id="agent-2",
        )
        assert outcome.success
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.COMPLETED
        got = await kernel._store.get_claim(claim.claim_id)
        assert got is not None and got.state is ClaimState.VERIFIED
        assert got.verdict_by == "agent-2"

    async def test_rejected_returns_in_progress(self, kernel):
        task, claim = await _delivered(kernel)
        outcome = await kernel.verify(
            task_id=task.task_id,
            claim_id=claim.claim_id,
            verdict="rejected",
            verifier_id="agent-2",
            reason="不够",
        )
        assert outcome.success
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.IN_PROGRESS
        got = await kernel._store.get_claim(claim.claim_id)
        assert got is not None and got.state is ClaimState.REJECTED

    async def test_self_approval_denied(self, kernel):
        """探针 2：approver 非空时 claimant 自批拒。"""
        verification = Verification(approver="human")
        task, claim = await _delivered(kernel, verification=verification, claimant="agent-1")
        outcome = await kernel.verify(
            task_id=task.task_id,
            claim_id=claim.claim_id,
            verdict="verified",
            verifier_id="agent-1",
        )
        assert not outcome.success
        # claim 状态未被污染
        got = await kernel._store.get_claim(claim.claim_id)
        assert got is not None and got.state is ClaimState.SUBMITTED

    async def test_verify_non_submitted_claim_denied(self, kernel):
        task, claim = await _delivered(kernel)
        await kernel.verify(
            task_id=task.task_id,
            claim_id=claim.claim_id,
            verdict="verified",
            verifier_id="agent-2",
        )
        outcome = await kernel.verify(
            task_id=task.task_id,
            claim_id=claim.claim_id,
            verdict="verified",
            verifier_id="agent-3",
        )
        assert not outcome.success

    async def test_verify_events(self, kernel):
        events: list[tuple] = []

        async def on_event(event: tuple) -> None:
            events.append(event)

        kernel._on_event = on_event
        task, claim = await _delivered(kernel)
        await kernel.verify(
            task_id=task.task_id,
            claim_id=claim.claim_id,
            verdict="verified",
            verifier_id="agent-2",
        )
        assert [e[0] for e in events] == ["task_delivered", "task_verified"]
        assert events[-1][3] is TaskStatus.DELIVERED  # previous_status

        task2, claim2 = await _delivered(kernel)
        await kernel.verify(
            task_id=task2.task_id,
            claim_id=claim2.claim_id,
            verdict="rejected",
            verifier_id="agent-2",
            reason="r",
        )
        assert events[-1][0] == "task_rejected"


class TestComplete:
    async def test_complete_without_verification(self, kernel):
        task = await kernel.create_task(project_id="p1", title="demo")
        outcome = await kernel.complete(task_id=task.task_id)
        assert outcome.success
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.COMPLETED

    async def test_complete_with_verification_denied(self, kernel):
        """探针 2：verification 非空时 complete 直通拒。"""
        task = await kernel.create_task(
            project_id="p1", title="demo", verification=Verification(evidence_min=1)
        )
        outcome = await kernel.complete(task_id=task.task_id)
        assert not outcome.success
        assert outcome.denial is not None
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.PENDING


class TestUpdateTask:
    async def test_update_status_guard(self, kernel):
        task = await kernel.create_task(project_id="p1", title="demo")
        for blocked in (TaskStatus.DELIVERED, TaskStatus.COMPLETED):
            outcome = await kernel.update_task(task.task_id, status=blocked)
            assert not outcome.success

        outcome = await kernel.update_task(task.task_id, status=TaskStatus.IN_PROGRESS)
        assert outcome.success
        fresh = await kernel._store.get_task(task.task_id)
        assert fresh is not None and fresh.status is TaskStatus.IN_PROGRESS

    async def test_update_optimistic_lock(self, kernel):
        task = await kernel.create_task(project_id="p1", title="demo")
        outcome = await kernel.update_task(task.task_id, title="v2", expected_version=99)
        assert not outcome.success
        outcome = await kernel.update_task(task.task_id, title="v2", expected_version=1)
        assert outcome.success

    async def test_update_missing_task(self, kernel):
        outcome = await kernel.update_task("ghost", title="x")
        assert not outcome.success
