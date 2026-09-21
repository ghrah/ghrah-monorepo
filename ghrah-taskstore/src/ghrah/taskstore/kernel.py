# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""内核 facade：命令/查询面 + impure 边界（跑 checker、取钟、分配 id）。

边界/转移分离（确定性纪律）：本模块是唯一的世界读取点——checker 在 submit
边界执行并冻结入 claim，时间戳与 id 由注入的 Clock / IdFactory 分配；
transition.py 消费冻结结果做纯转移。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ghrah.plugin.registry import PluginRegistry

from ghrah.taskstore.checkers import CheckerRegistry, CheckOutcome, run_checker
from ghrah.taskstore.errors import TaskNotFoundError
from ghrah.taskstore.models import (
    ClaimantType,
    ClaimRecord,
    ClaimState,
    EvidenceRecord,
    Outcome,
    Provenance,
    TaskRecord,
    TaskStatus,
    Verification,
    VerificationGaps,
)
from ghrah.taskstore.store import TaskStore
from ghrah.taskstore.transition import complete_outcome, submit_outcome, verify_outcome

__all__ = [
    "Clock",
    "IdFactory",
    "KernelEvent",
    "OnEvent",
    "PluginRegistryProvider",
    "TaskStoreKernel",
]

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]
PluginRegistryProvider = Callable[[], PluginRegistry]

# 事件回调：(event_type, task, claim, previous_status, reason)
KernelEvent = tuple[str, TaskRecord, ClaimRecord, TaskStatus | None, str | None]
OnEvent = Callable[[KernelEvent], Awaitable[None]] | Callable[[KernelEvent], None]

_EVENT_DELIVERED = "task_delivered"
_EVENT_VERIFIED = "task_verified"
_EVENT_REJECTED = "task_rejected"


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _default_id_factory() -> str:
    return uuid4().hex


class TaskStoreKernel:
    """任务归因内核 facade（三表唯一写路径）。

    Args:
        store: sqlite 权威。
        checkers: CheckerRegistry（装配层注入）。
        plugin_registry_provider: 惰性求值已挂载插件注册表快照（submit 边界调用）。
        clock: 时间源（默认真实 UTC；测试注入固定钟）。
        id_factory: id 源（默认 uuid4().hex；测试注入计数器）。
        on_event: 事件回调（task_delivered / task_verified / task_rejected）。
    """

    def __init__(
        self,
        store: TaskStore,
        checkers: CheckerRegistry,
        *,
        plugin_registry_provider: PluginRegistryProvider | None = None,
        clock: Clock = _default_clock,
        id_factory: IdFactory = _default_id_factory,
        on_event: OnEvent | None = None,
    ) -> None:
        self._store = store
        self._checkers = checkers
        self._plugin_registry_provider = plugin_registry_provider
        self._clock = clock
        self._id_factory = id_factory
        self._on_event = on_event

    # ─── 命令面（create/update 不上 P0 wire，D3/D17）───

    async def create_task(
        self,
        *,
        project_id: str,
        title: str,
        description: str = "",
        acceptance: str | None = None,
        metadata: dict[str, Any] | None = None,
        verification: Verification | None = None,
    ) -> TaskRecord:
        """创建内核 task（seq 由锁内 MAX+1 分配；status 恒 pending）。"""

        now = self._clock()
        seq = await self._store.next_seq(project_id)
        record = TaskRecord(
            task_id=self._id_factory(),
            project_id=project_id,
            seq=seq,
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            acceptance=acceptance,
            metadata=dict(metadata) if metadata else {},
            verification=verification,
            created_at=now,
            updated_at=now,
        )
        await self._store.insert_task(record)
        return record

    async def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        acceptance: str | None = None,
        metadata: dict[str, Any] | None = None,
        verification: Verification | None = None,
        status: TaskStatus | None = None,
        expected_version: int | None = None,
    ) -> Outcome:
        """最小 update：乐观锁 + 状态守卫（禁改 delivered/completed，纪律 6）。"""

        if status is not None and status in (TaskStatus.DELIVERED, TaskStatus.COMPLETED):
            return Outcome.denied(
                VerificationGaps(),
                f"status {status.value} must go through submit/verify or complete channel",
            )

        def mutate(current: TaskRecord) -> TaskRecord:
            return current.model_copy(
                update={
                    **({"title": title} if title is not None else {}),
                    **({"description": description} if description is not None else {}),
                    **({"acceptance": acceptance} if acceptance is not None else {}),
                    **({"metadata": dict(metadata)} if metadata is not None else {}),
                    **({"verification": verification} if verification is not None else {}),
                    **({"status": status} if status is not None else {}),
                    "updated_at": self._clock(),
                }
            )

        try:
            updated = await self._store.update_task(
                task_id, expected_version=expected_version, mutator=mutate
            )
        except Exception as exc:  # noqa: BLE001 — 乐观锁等错误回 Outcome
            return Outcome.ok(None).model_copy(update={"success": False, "error": str(exc)})
        if updated is None:
            return Outcome(success=False, error=f"task not found: {task_id}")
        return Outcome.ok(updated)

    # ─── 归因命令面 ───

    async def submit_completion(
        self,
        *,
        task_id: str,
        claimant_type: ClaimantType = ClaimantType.AGENT,
        claimant_id: str,
        claimant_name: str | None = None,
        note: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        provenance: Provenance | None = None,
        expected_version: int | None = None,
    ) -> Outcome:
        """submit_completion：建 claim → verification 评估 → delivered | Denial。

        边界（impure）：落证据、跑 checker、取钟、分配 id；
        转移（pure）：transition.submit_outcome 消费冻结结果。
        """

        task = await self._store.get_task(task_id, include_deleted=True)
        if task is None:
            raise TaskNotFoundError(task_id)

        verification = task.verification
        evidence_inputs = evidence or []
        now = self._clock()

        # 边界：证据落库（upsert 复用，冻结快照供 checker）
        frozen_evidence: list[EvidenceRecord] = []
        for item in evidence_inputs:
            record = EvidenceRecord(
                evidence_id=self._id_factory(),
                kind=item["kind"],
                ref=item["ref"],
                digest=item.get("digest"),
                payload=dict(item.get("payload") or {}),
                created_by=claimant_id,
                created_at=now,
            )
            stored, _ = await self._store.upsert_evidence(record)
            frozen_evidence.append(stored)

        # 边界：跑 checker（世界答案在此冻结，重放不重跑）
        frozen_checks: list[CheckOutcome] = []
        check_candidates: dict[str, list[str]] = {}
        wanted_checks = sorted(set(verification.checks)) if verification else []
        for name in wanted_checks:
            candidates = self._checker_candidates(name)
            check_candidates[name] = candidates
            checker = self._checkers.resolve(name)
            if checker is None:
                continue  # 未命中：转移记 missing_checks（含候选）
            task_view = task.model_dump(mode="json")
            evidence_view = {"items": [e.model_dump(mode="json") for e in frozen_evidence]}
            frozen_checks.append(
                run_checker(checker, name, evidence=evidence_view, task=task_view, config={})
            )

        has_open_claim = bool(
            await self._store.list_claims(
                task_id=task_id, state=ClaimState.SUBMITTED.value, limit=1
            )
        )
        outcome = submit_outcome(
            task,
            verification,
            frozen_evidence,
            frozen_checks,
            check_candidates,
            claim_id=self._id_factory(),
            claimant_type=claimant_type,
            claimant_id=claimant_id,
            claimant_name=claimant_name,
            note=note,
            provenance=provenance,
            created_at=now,
            has_open_claim=has_open_claim,
        )
        if not outcome.success:
            return outcome

        # 落库：claim + task 状态（乐观锁）
        new_claim: ClaimRecord = outcome.data["claim"]
        new_status: TaskStatus = outcome.data["task_status"]
        superseded: bool = outcome.data["superseded"]
        await self._store.insert_claim(new_claim)
        if superseded:
            previous_claims = await self._store.list_claims(
                task_id=task_id, state=ClaimState.SUBMITTED.value, limit=100
            )
            for old in previous_claims:
                if old.claim_id == new_claim.claim_id:
                    continue
                await self._store.update_claim(
                    old.claim_id,
                    expected_version=None,
                    mutator=lambda c: c.model_copy(update={"state": ClaimState.SUPERSEDED}),
                )
        previous_status = task.status

        def mutate(current: TaskRecord) -> TaskRecord:
            return current.model_copy(update={"status": new_status, "updated_at": self._clock()})

        updated = await self._store.update_task(
            task_id, expected_version=expected_version, mutator=mutate
        )
        if updated is None:
            return Outcome(success=False, error=f"task not found: {task_id}")
        await self._emit(_EVENT_DELIVERED, updated, new_claim, previous_status, None)
        return outcome

    async def verify(
        self,
        *,
        task_id: str,
        claim_id: str,
        verdict: str,
        verifier_id: str,
        reason: str | None = None,
        expected_version: int | None = None,
    ) -> Outcome:
        """verify：submitted claim 的验收裁决（执行者独立原则内嵌转移）。"""

        task = await self._store.get_task(task_id, include_deleted=True)
        if task is None:
            raise TaskNotFoundError(task_id)
        claim = await self._store.get_claim(claim_id)
        if claim is None or claim.task_id != task_id:
            return Outcome(success=False, error=f"claim not found: {claim_id}")

        now = self._clock()
        outcome = verify_outcome(
            task,
            claim,
            task.verification,
            verdict=verdict,
            verifier_id=verifier_id,
            reason=reason,
            verified_at=now,
        )
        if not outcome.success:
            return outcome

        new_claim: ClaimRecord = outcome.data["claim"]
        new_status: TaskStatus = outcome.data["task_status"]
        previous_status = task.status

        await self._store.update_claim(
            claim_id,
            expected_version=None,
            mutator=lambda c: c.model_copy(
                update={
                    "state": new_claim.state,
                    "verdict_by": verifier_id,
                    "verdict_at": now,
                    "verdict_reason": reason,
                }
            ),
        )
        updated = await self._store.update_task(
            task_id,
            expected_version=expected_version,
            mutator=lambda c: c.model_copy(update={"status": new_status, "updated_at": now}),
        )
        if updated is None:
            return Outcome(success=False, error=f"task not found: {task_id}")
        event = _EVENT_VERIFIED if new_status is TaskStatus.COMPLETED else _EVENT_REJECTED
        await self._emit(event, updated, new_claim, previous_status, reason)
        return outcome

    async def complete(self, *, task_id: str, expected_version: int | None = None) -> Outcome:
        """complete 快捷通道：verification 非空 → Denial。"""

        task = await self._store.get_task(task_id, include_deleted=True)
        if task is None:
            raise TaskNotFoundError(task_id)
        outcome = complete_outcome(task, task.verification)
        if not outcome.success:
            return outcome

        new_status: TaskStatus = outcome.data["task_status"]
        now = self._clock()
        updated = await self._store.update_task(
            task_id,
            expected_version=expected_version,
            mutator=lambda c: c.model_copy(update={"status": new_status, "updated_at": now}),
        )
        if updated is None:
            return Outcome(success=False, error=f"task not found: {task_id}")
        return Outcome.ok(updated)

    # ─── 查询面 ───

    async def list_claims(
        self,
        *,
        task_id: str | None = None,
        claimant_id: str | None = None,
        state: str | list[str] | None = None,
        limit: int = 100,
    ) -> list[ClaimRecord]:
        """列出 claim（可选过滤）。"""

        return await self._store.list_claims(
            task_id=task_id, claimant_id=claimant_id, state=state, limit=limit
        )

    async def dump(
        self,
        *,
        project_id: str | None = None,
        include_deleted: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """全量快照（D18②：limit 仅限 tasks，claims/evidence 随所选 tasks 收敛）。"""

        tasks, claims, evidence = await self._store.dump(
            project_id=project_id, include_deleted=include_deleted, limit=limit
        )
        return {
            "tasks": [t.model_dump(mode="json") for t in tasks],
            "claims": [c.model_dump(mode="json") for c in claims],
            "evidence": [e.model_dump(mode="json") for e in evidence],
        }

    # ─── 内部 ───

    def _checker_candidates(self, name: str) -> list[str]:
        """惰性求值已挂载插件的 checker 候选（注册表不在场 → 空清单）。"""

        if self._plugin_registry_provider is None:
            return []
        try:
            registry = self._plugin_registry_provider()
        except Exception:  # noqa: BLE001 — 候选求解失败按未命中处理
            logger.warning("plugin registry provider failed; no checker candidates.")
            return []
        return registry.resolve_checker(name)

    async def _emit(
        self,
        event_type: str,
        task: TaskRecord,
        claim: ClaimRecord,
        previous_status: TaskStatus | None,
        reason: str | None,
    ) -> None:
        if self._on_event is None:
            return
        result = self._on_event((event_type, task, claim, previous_status, reason))
        if isinstance(result, Awaitable):
            await result
