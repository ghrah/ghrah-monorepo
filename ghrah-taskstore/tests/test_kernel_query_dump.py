# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""kernel 查询面测试：list_claims 过滤 + dump 全量（D18② limit 语义）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghrah.taskstore.checkers import CheckerRegistry
from ghrah.taskstore.kernel import TaskStoreKernel
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


async def _seed(kernel):
    t1 = await kernel.create_task(project_id="p1", title="t1")
    t2 = await kernel.create_task(project_id="p1", title="t2")
    t3 = await kernel.create_task(project_id="p2", title="t3")
    await kernel.submit_completion(task_id=t1.task_id, claimant_id="a1", evidence=[])
    await kernel.submit_completion(task_id=t2.task_id, claimant_id="a2", evidence=[])
    return t1, t2, t3


class TestListClaims:
    async def test_filters(self, kernel):
        t1, t2, _ = await _seed(kernel)
        assert len(await kernel.list_claims()) == 2
        assert [c.task_id for c in await kernel.list_claims(task_id=t1.task_id)] == [t1.task_id]
        assert len(await kernel.list_claims(claimant_id="a2")) == 1
        assert len(await kernel.list_claims(state="verified")) == 0
        assert len(await kernel.list_claims(state=["submitted", "rejected"])) == 2
        assert len(await kernel.list_claims(limit=1)) == 1

    async def test_claim_carries_provenance(self, kernel):
        """探针 1 切面：claim 携带 provenance（agent/session/branch/node）。"""
        task = await kernel.create_task(project_id="p1", title="demo")
        outcome = await kernel.submit_completion(
            task_id=task.task_id,
            claimant_id="a1",
            provenance={
                "agent_id": "ag-1",
                "session_id": "s-1",
                "branch_id": None,
                "node_id": None,
            },
        )
        assert outcome.success
        claims = await kernel.list_claims(task_id=task.task_id)
        assert claims[0].provenance is not None
        assert claims[0].provenance.agent_id == "ag-1"


class TestDump:
    async def test_dump_full_roundtrip(self, kernel):
        t1, t2, t3 = await _seed(kernel)
        result = await kernel.dump()
        assert len(result["tasks"]) == 3
        assert len(result["claims"]) == 2
        assert result["evidence"] == []
        assert [t["title"] for t in result["tasks"]] == ["t1", "t2", "t3"]

    async def test_dump_project_filter(self, kernel):
        await _seed(kernel)
        result = await kernel.dump(project_id="p2")
        assert [t["project_id"] for t in result["tasks"]] == ["p2"]
        assert result["claims"] == []

    async def test_dump_limit_scopes_claims_and_evidence(self, kernel):
        """D18②：limit 仅限 tasks，claims/evidence 随所选 tasks 收敛。"""
        t1 = await kernel.create_task(project_id="p1", title="t1")
        t2 = await kernel.create_task(project_id="p1", title="t2")
        await kernel.submit_completion(
            task_id=t1.task_id,
            claimant_id="a1",
            evidence=[{"kind": "git_commit", "ref": "r1", "digest": "d1"}],
        )
        await kernel.submit_completion(task_id=t2.task_id, claimant_id="a2", evidence=[])
        full = await kernel.dump()
        assert len(full["tasks"]) == 2 and len(full["claims"]) == 2 and len(full["evidence"]) == 1

        limited = await kernel.dump(limit=1)
        assert len(limited["tasks"]) == 1
        assert len(limited["claims"]) == 1
        assert limited["claims"][0]["task_id"] == limited["tasks"][0]["task_id"]
        assert len(limited["evidence"]) == len(limited["claims"][0]["evidence_ids"])

    async def test_dump_claim_embeds_evidence(self, kernel):
        """TaskClaimPayload 语义：claim 内嵌 evidence 供单命令重建。"""
        task = await kernel.create_task(project_id="p1", title="demo")
        await kernel.submit_completion(
            task_id=task.task_id,
            claimant_id="a1",
            evidence=[{"kind": "git_commit", "ref": "r1", "digest": "d1"}],
        )
        result = await kernel.dump()
        claim = result["claims"][0]
        evidence_ids = [e["evidence_id"] for e in result["evidence"]]
        assert claim["evidence_ids"] == evidence_ids
