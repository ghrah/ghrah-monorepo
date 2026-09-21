# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""重放探针（验收③）：同命令日志两次重放终态逐位一致；同一 Denial 离线复现。

注入计数器 IdFactory + 固定 Clock + 确定性 checker——生产默认真实钟/uuid4，
仅测试注入确定性实现（探针 14 最小版）。命令日志用 (project_id, seq) 锚定
task、claim 索引锚定 claim，不依赖具体 id 值（两个全新内核 id 序一致，
但锚点让日志与 id 分配解耦）。
"""

from __future__ import annotations

import copy
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ghrah.taskstore.checkers import CheckerRegistry
from ghrah.taskstore.kernel import TaskStoreKernel
from ghrah.taskstore.models import Verification
from ghrah.taskstore.store import TaskStore


class FixedClock:
    """固定钟：命令序驱动（第 N 次调用 = 基准 + N 秒），确定性。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return datetime(2026, 9, 21, 12, 0, self.calls, tzinfo=UTC)


class CounterIds:
    """计数器 id：前缀-N（跨内核实例从零开始，两次重放同序）。"""

    def __init__(self, prefix: str) -> None:
        self.n = 0
        self.prefix = prefix

    def __call__(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n}"


def _deterministic_checker(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
    kinds = sorted({e.get("kind") for e in evidence["items"]})
    return {"passed": "git_commit" in kinds, "detail": None}


def _command_log() -> list[dict[str, Any]]:
    """命令日志（纯数据；task 以 (project_id, seq) 锚定，claim 以列表索引锚定）。"""

    return [
        {
            "cmd": "create",
            "project_id": "p1",
            "title": "task-a",
            "verification": {
                "evidence_min": 1,
                "evidence_kinds": ["git_commit"],
                "checks": ["commit_in_repo"],
            },
        },
        {"cmd": "create", "project_id": "p1", "title": "task-b", "verification": None},
        {"cmd": "create", "project_id": "p2", "title": "task-c", "verification": None},
        # task-a：无证据 submit（Denial）
        {"cmd": "submit", "task": ("p1", 1), "claimant_id": "agent-1", "evidence": []},
        # task-a：补证据 submit（Ok）
        {
            "cmd": "submit",
            "task": ("p1", 1),
            "claimant_id": "agent-1",
            "evidence": [{"kind": "git_commit", "ref": "abc", "digest": "d1"}],
        },
        # task-a：他人 verify → completed
        {
            "cmd": "verify",
            "task": ("p1", 1),
            "claim_index": 0,
            "verdict": "verified",
            "verifier_id": "agent-2",
        },
        # task-b：submit（无 verification 直接过）→ verify rejected → 再 submit → verify
        {"cmd": "submit", "task": ("p1", 2), "claimant_id": "agent-1", "evidence": []},
        {
            "cmd": "verify",
            "task": ("p1", 2),
            "claim_index": 0,
            "verdict": "rejected",
            "verifier_id": "agent-2",
            "reason": "redo",
        },
        {"cmd": "submit", "task": ("p1", 2), "claimant_id": "agent-1", "evidence": []},
        {
            "cmd": "verify",
            "task": ("p1", 2),
            "claim_index": -1,
            "verdict": "verified",
            "verifier_id": "agent-3",
        },
        # task-c：complete 直通
        {"cmd": "complete", "task": ("p2", 1)},
    ]


async def _replay(db_path: Path, log: list[dict[str, Any]]) -> dict[str, Any]:
    """全新内核重放命令日志，返回终态 dump + Denial 清单（逐位可比）。"""

    store = TaskStore(db_path)
    await store.start()
    registry = CheckerRegistry()
    registry.register("commit_in_repo", _deterministic_checker)
    kernel = TaskStoreKernel(store, registry, clock=FixedClock(), id_factory=CounterIds("t"))
    denials: list[dict[str, Any]] = []
    try:
        for entry in log:
            cmd = entry["cmd"]
            if cmd == "create":
                verification = None
                if entry.get("verification") is not None:
                    verification = Verification.model_validate(entry["verification"])
                await kernel.create_task(
                    project_id=entry["project_id"],
                    title=entry["title"],
                    verification=verification,
                )
                continue

            # (project_id, seq) → task_id
            project_id, seq = entry["task"]
            tasks = await store.list_tasks(project_id=project_id)
            task = next(t for t in tasks if t.seq == seq)

            if cmd == "submit":
                outcome = await kernel.submit_completion(
                    task_id=task.task_id,
                    claimant_id=entry["claimant_id"],
                    evidence=entry.get("evidence") or [],
                )
                if not outcome.success:
                    denials.append(outcome.model_dump(mode="json"))
            elif cmd == "verify":
                claims = await kernel.list_claims(task_id=task.task_id, limit=100)
                claim = claims[entry["claim_index"]]
                outcome = await kernel.verify(
                    task_id=task.task_id,
                    claim_id=claim.claim_id,
                    verdict=entry["verdict"],
                    verifier_id=entry["verifier_id"],
                    reason=entry.get("reason"),
                )
                if not outcome.success:
                    denials.append(outcome.model_dump(mode="json"))
            elif cmd == "complete":
                outcome = await kernel.complete(task_id=task.task_id)
                if not outcome.success:
                    denials.append(outcome.model_dump(mode="json"))
        dump = await kernel.dump()
        return {"dump": dump, "denials": denials}
    finally:
        await store.stop()


async def test_replay_bit_identical(tmp_path: Any) -> None:
    """验收③（探针 14）：同命令日志驱动两个全新内核，dump 终态逐位一致。"""
    log = _command_log()
    first = await _replay(tmp_path / "a.sqlite3", log)
    second = await _replay(tmp_path / "b.sqlite3", log)
    assert first["dump"] == second["dump"]
    assert first["denials"] == second["denials"]
    # 日志含一次 Denial（无证据 submit）且两核一致
    assert len(first["denials"]) == 1
    assert first["denials"][0]["denial"]["evidence_need"] == 1


async def test_denial_offline_reproducible() -> None:
    """探针 14 补充：同一 Denial 两次离线复现（纯转移消费冻结结果，不重跑 checker）。"""
    log: list[dict[str, Any]] = [
        {
            "cmd": "create",
            "project_id": "p1",
            "title": "x",
            "verification": {
                "evidence_min": 2,
                "evidence_kinds": ["screenshot"],
                "checks": ["ghost_checker"],
            },
        },
        {"cmd": "submit", "task": ("p1", 1), "claimant_id": "a", "evidence": []},
    ]
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        first = await _replay(Path(d1) / "a.sqlite3", log)
        second = await _replay(Path(d2) / "b.sqlite3", log)
    d1 = first["denials"][0]
    d2 = second["denials"][0]
    assert d1 == d2
    # 缺口完整：计数差 + 缺 kind + 缺 checker（候选为空）
    assert d1["denial"]["evidence_have"] == 0
    assert d1["denial"]["evidence_need"] == 2
    assert d1["denial"]["missing_evidence_kinds"] == ["screenshot"]
    assert d1["denial"]["missing_checks"] == [{"checker": "ghost_checker", "candidates": []}]


async def test_checker_input_frozen_host_not_polluted(tmp_path: Any) -> None:
    """A16 探针（T11 层）：checker 修改入参 → TypeError 归一失败，宿主数据未污染。"""
    store = TaskStore(tmp_path / "k.sqlite3")
    await store.start()
    registry = CheckerRegistry()

    def mutating_checker(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
        evidence["items"].append({"kind": "forged"})  # type: ignore[union-attr]
        task["title"] = "tampered"  # type: ignore[index]
        return {"passed": True}

    registry.register("commit_in_repo", mutating_checker)
    kernel = TaskStoreKernel(store, registry, clock=FixedClock(), id_factory=CounterIds("t"))
    try:
        task = await kernel.create_task(
            project_id="p1",
            title="original",
            verification=Verification(evidence_min=1, checks=["commit_in_repo"]),
        )
        outcome = await kernel.submit_completion(
            task_id=task.task_id,
            claimant_id="a",
            evidence=[{"kind": "git_commit", "ref": "r"}],
        )
        # checker 尝试修改冻结入参 → TypeError → 归一 failed → submit 被 Denial
        assert not outcome.success
        assert outcome.denial is not None
        assert outcome.denial.failed_checks[0].checker == "commit_in_repo"
        fresh = await store.get_task(task.task_id)
        assert fresh is not None
        assert fresh.title == "original"  # 宿主 task 未被污染
        dump = await kernel.dump()
        deep = copy.deepcopy(dump)
        assert deep["tasks"][0]["status"] == "pending"
    finally:
        await store.stop()
