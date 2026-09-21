# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""store 测试：DDL 幂等、乐观锁、软删、seq 单调、evidence 去重、dump 收敛。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghrah.taskstore.errors import ConcurrentModificationError
from ghrah.taskstore.models import (
    ClaimRecord,
    ClaimState,
    EvidenceRecord,
    TaskRecord,
    TaskStatus,
)
from ghrah.taskstore.store import TaskStore

NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


def _task(task_id: str = "t1", project_id: str = "p1", seq: int = 1) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        project_id=project_id,
        seq=seq,
        title="demo",
        status=TaskStatus.IN_PROGRESS,
        created_at=NOW,
        updated_at=NOW,
    )


def _claim(claim_id: str = "c1", task_id: str = "t1") -> ClaimRecord:
    return ClaimRecord(
        claim_id=claim_id,
        task_id=task_id,
        claimant_id="agent-1",
        evidence_ids=["e1"],
        state=ClaimState.SUBMITTED,
        created_at=NOW,
    )


def _evidence(evidence_id: str = "e1", ref: str = "commit-abc") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind="git_commit",
        ref=ref,
        digest="sha256:deadbeef",
        created_by="agent-1",
        created_at=NOW,
    )


@pytest.fixture
async def store(tmp_path):
    s = TaskStore(tmp_path / "taskstore.sqlite3")
    await s.start()
    yield s
    await s.stop()


class TestLifecycle:
    async def test_start_idempotent(self, store, tmp_path):
        """幂等 DDL：同一路径二次 start 不炸且数据保留。"""
        other = TaskStore(store._db_path)
        await other.start()
        try:
            await other.insert_task(_task("t9", seq=9))
            got = await other.get_task("t9")
            assert got is not None
        finally:
            await other.stop()

    async def test_double_start_same_instance(self, store):
        await store.start()
        assert await store.get_task("nope") is None


class TestTasks:
    async def test_seq_monotonic_per_project(self, store):
        assert await store.next_seq("p1") == 1
        await store.insert_task(_task("t1", seq=1))
        assert await store.next_seq("p1") == 2
        await store.insert_task(_task("t2", seq=2))
        assert await store.next_seq("p1") == 3
        assert await store.next_seq("p2") == 1

    async def test_optimistic_lock_conflict(self, store):
        await store.insert_task(_task())
        with pytest.raises(ConcurrentModificationError):
            await store.update_task("t1", expected_version=99, mutator=lambda t: t)
        updated = await store.update_task(
            "t1", expected_version=1, mutator=lambda t: t.model_copy(update={"title": "x2"})
        )
        assert updated is not None and updated.version == 2 and updated.title == "x2"

    async def test_update_missing_returns_none(self, store):
        assert await store.update_task("ghost", expected_version=None, mutator=lambda t: t) is None

    async def test_soft_delete(self, store):
        await store.insert_task(_task())
        assert await store.soft_delete_task("t1", deleted_at=NOW) is True
        assert await store.get_task("t1") is None
        assert (await store.get_task("t1", include_deleted=True)) is not None
        assert await store.soft_delete_task("t1", deleted_at=NOW) is False

    async def test_list_tasks_order_and_limit(self, store):
        for i in range(1, 5):
            await store.insert_task(_task(f"t{i}", seq=i))
        tasks = await store.list_tasks()
        assert [t.seq for t in tasks] == [1, 2, 3, 4]
        limited = await store.list_tasks(limit=2)
        assert [t.seq for t in limited] == [1, 2]
        assert len(await store.list_tasks(project_id="other")) == 0


class TestEvidence:
    async def test_upsert_reuse(self, store):
        first, inserted = await store.upsert_evidence(_evidence())
        assert inserted is True
        second_ev = _evidence(evidence_id="e-other", ref="commit-abc")
        second_ev.created_by = "agent-2"
        second, inserted2 = await store.upsert_evidence(second_ev)
        assert inserted2 is False
        assert second.evidence_id == first.evidence_id
        assert second.created_by == "agent-1"  # 首写为准，复用不改

    async def test_different_digest_not_reused(self, store):
        await store.upsert_evidence(_evidence())
        other = _evidence(evidence_id="e2", ref="commit-abc")
        other.digest = "sha256:other"
        _, inserted = await store.upsert_evidence(other)
        assert inserted is True

    async def test_list_by_ids_preserves_order(self, store):
        await store.upsert_evidence(_evidence("e1", "ref-1"))
        await store.upsert_evidence(_evidence("e2", "ref-2"))
        got = await store.list_evidence_by_ids(["e2", "e1"])
        assert [e.evidence_id for e in got] == ["e2", "e1"]
        assert await store.list_evidence_by_ids([]) == []


class TestClaimsAndDump:
    async def test_claim_roundtrip(self, store):
        await store.insert_task(_task())
        await store.insert_claim(_claim())
        got = await store.get_claim("c1")
        assert got is not None and got.evidence_ids == ["e1"]
        listed = await store.list_claims(task_id="t1")
        assert [c.claim_id for c in listed] == ["c1"]
        assert await store.list_claims(task_id="t1", state="verified") == []

    async def test_dump_scoped_to_tasks(self, store):
        """D18②：claims/evidence 随所选 tasks 收敛。"""
        await store.insert_task(_task("t1", seq=1))
        await store.insert_task(_task("t2", seq=2))
        await store.insert_claim(_claim("c1", "t1"))
        await store.insert_claim(_claim("c2", "t2"))
        await store.upsert_evidence(_evidence("e1", "ref-1"))
        tasks, claims, evidence = await store.dump()
        assert len(tasks) == 2 and len(claims) == 2 and len(evidence) == 1

        tasks_limited, claims_limited, evidence_limited = await store.dump(limit=1)
        assert [t.task_id for t in tasks_limited] == ["t1"]
        assert [c.claim_id for c in claims_limited] == ["c1"]
        assert [e.evidence_id for e in evidence_limited] == ["e1"]

    async def test_dump_respects_include_deleted(self, store):
        await store.insert_task(_task("t1", seq=1))
        await store.soft_delete_task("t1", deleted_at=NOW)
        tasks, claims, evidence = await store.dump()
        assert tasks == [] and claims == [] and evidence == []
        tasks, _, _ = await store.dump(include_deleted=True)
        assert [t.task_id for t in tasks] == ["t1"]

    async def test_store_no_hidden_clock_or_id(self, store):
        """零钟读：固定注入记录往返逐位一致（时间戳由调用方注入）。"""
        task = _task("t1", seq=1)
        await store.insert_task(task)
        got = await store.get_task("t1")
        assert got == task
        await store.insert_claim(_claim())
        got_claim = await store.get_claim("c1")
        assert got_claim == _claim()
