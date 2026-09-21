# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""任务归因内核 unit（builtin 链一等 unit，挂载 TaskStoreKernel）。

仅注册 4 归因命令（TASK_ATTRIBUTION_COMMANDS）：submit/verify 走内核转移，
list_claims / dump 走查询面。Denial 形状冻结（D18①）：``success=False`` +
``data={"gaps": ...}`` + error。事件映射：内核回调 → TaskClaimEventPayload
→ ``ctx.emit("event/<type>", ...)``（websocket endpoint 全集双前缀转发）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ghrah.protocol.payloads.task import (
    TaskClaimEventPayload,
    TaskClaimListPayload,
    TaskClaimListResultPayload,
    TaskClaimPayload,
    TaskDumpPayload,
    TaskDumpResultPayload,
    TaskEvidencePayload,
    TaskInfoPayload,
    TaskSubmitCompletionPayload,
    TaskVerificationGapsPayload,
    TaskVerifyPayload,
)
from ghrah.protocol.types import ClaimantType, TaskStatus
from ghrah.taskstore.checkers import CheckerRegistry
from ghrah.taskstore.kernel import TaskStoreKernel
from ghrah.taskstore.models import ClaimRecord, EvidenceRecord, TaskRecord
from ghrah.taskstore.store import TaskStore

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.plugin_session import PLUGIN_SESSION_SERVICE
from ghrah.subject.runtime.service_keys import (
    TASKSTORE_CHECKERS,
    TASKSTORE_SERVICE,
)
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import TASK_ATTRIBUTION_COMMANDS

if TYPE_CHECKING:
    pass  # type: ignore[import-untyped]

__all__ = ["TaskStoreUnit"]

logger = logging.getLogger(__name__)

_EVENT_TYPES = ("task_delivered", "task_verified", "task_rejected")


class TaskStoreUnit(SubjectUnit):
    """任务归因内核宿主（三表唯一权威的进程内入口）。"""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ctx: Any | None = None
        self._store: TaskStore | None = None
        self._kernel: TaskStoreKernel | None = None
        self._meta = UnitMeta(
            name="taskstore",
            routes=RouteSpec(commands=TASK_ATTRIBUTION_COMMANDS),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> TaskStoreKernel:
        """内核 facade（经 TASKSTORE_SERVICE 服务键暴露，D17：P0 内核 task 创建入口）。"""

        if self._kernel is None:
            raise RuntimeError("TaskStoreUnit has not been initialized.")
        return self._kernel

    async def init(self, ctx: Any) -> None:
        self._ctx = ctx
        self._store = TaskStore(self._config.taskstore.db_path)
        checkers = CheckerRegistry()

        def plugin_registry_provider() -> Any:
            # 惰性解析（D12/T9）：PluginSession 在 _assemble_plugins 才挂载，
            # 此回调只在 submit 边界被调用，即时构造注册表快照。
            from ghrah.plugin.registry import PluginRegistry

            session = ctx.get(PLUGIN_SESSION_SERVICE.name, strict=False)
            if session is None:
                return PluginRegistry([])
            return PluginRegistry(list(session.state.specs.values()))

        self._kernel = TaskStoreKernel(
            self._store,
            checkers,
            plugin_registry_provider=plugin_registry_provider,
            on_event=self._on_kernel_event,
        )
        ctx.provide(TASKSTORE_SERVICE.name, self._kernel)
        ctx.provide(TASKSTORE_CHECKERS.name, checkers)

    async def start(self) -> None:
        if self._store is not None:
            await self._store.start()

    async def stop(self) -> None:
        if self._store is not None:
            await self._store.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        del cmd_ctx
        kernel = self.service
        try:
            if command == "task_submit_completion":
                parsed = TaskSubmitCompletionPayload.model_validate(payload)
                outcome = await kernel.submit_completion(
                    task_id=parsed.task_id,
                    claimant_type=ClaimantType(parsed.claimant_type),
                    claimant_id=parsed.claimant_id,
                    claimant_name=parsed.claimant_name,
                    note=parsed.note,
                    evidence=[e.model_dump() for e in parsed.evidence],
                    provenance=parsed.provenance,
                    expected_version=parsed.expected_version,
                )
                return self._outcome_to_result(command, outcome)
            if command == "task_verify":
                parsed = TaskVerifyPayload.model_validate(payload)
                outcome = await kernel.verify(
                    task_id=parsed.task_id,
                    claim_id=parsed.claim_id,
                    verdict=parsed.verdict,
                    verifier_id=parsed.verifier_id,
                    reason=parsed.reason,
                    expected_version=parsed.expected_version,
                )
                return self._outcome_to_result(command, outcome)
            if command == "task_list_claims":
                parsed = TaskClaimListPayload.model_validate(payload)
                claims = await kernel.list_claims(
                    task_id=parsed.task_id,
                    claimant_id=parsed.claimant_id,
                    state=parsed.state,
                    limit=parsed.limit,
                )
                embedded = [await self._evidence_for_claim(c) for c in claims]
                data = TaskClaimListResultPayload(
                    claims=[
                        self._claim_to_payload(c, evidence=e)
                        for c, e in zip(claims, embedded, strict=True)
                    ],
                    count=len(claims),
                )
                return {"success": True, "data": data.model_dump(mode="json")}
            if command == "task_dump":
                parsed = TaskDumpPayload.model_validate(payload)
                dump = await kernel.dump(
                    project_id=parsed.project_id,
                    include_deleted=parsed.include_deleted,
                    limit=parsed.limit,
                )
                data = self._dump_to_payload(dump)
                return {"success": True, "data": data.model_dump(mode="json")}
            return {"success": False, "error": f"Unknown command: {command}"}
        except Exception as exc:  # noqa: BLE001 — 非法载荷/内部错误回执不炸宿主
            logger.warning("taskstore command '%s' failed: %s", command, exc)
            return {"success": False, "error": f"{command} failed: {exc}"}

    # ─── 内核回调 → wire 事件 ───

    async def _on_kernel_event(self, event: Any) -> None:
        """内核 (event_type, task, claim, previous_status, reason) → ctx.emit。"""

        event_type, task, claim, previous_status, reason = event
        if self._ctx is None:
            return
        evidence = await self._evidence_for_claim(claim)
        payload = self._event_to_payload(task, claim, evidence, previous_status, reason)
        self._ctx.emit(f"event/{event_type}", payload.model_dump(mode="json"))

    async def _evidence_for_claim(self, claim: ClaimRecord) -> list[TaskEvidencePayload]:
        """claim 内嵌 evidence（探针 1：单命令取回归因链）。"""

        if self._store is None or not claim.evidence_ids:
            return []
        records = await self._store.list_evidence_by_ids(claim.evidence_ids)
        return [
            TaskEvidencePayload(
                evidence_id=e.evidence_id,
                kind=e.kind,
                ref=e.ref,
                digest=e.digest,
                payload=e.payload,
                created_by=e.created_by,
                created_at=e.created_at.isoformat(),
            )
            for e in records
        ]

    def _event_to_payload(
        self,
        task: TaskRecord,
        claim: ClaimRecord,
        evidence: list[TaskEvidencePayload],
        previous_status: TaskStatus | None,
        reason: str | None,
    ) -> TaskClaimEventPayload:
        return TaskClaimEventPayload(
            task=self._task_to_payload(task),
            claim=self._claim_to_payload(claim, evidence=evidence),
            previous_status=TaskStatus(previous_status.value) if previous_status else None,
            reason=reason,
        )

    # ─── Outcome → command_result（Denial 形状冻结 D18①）───

    def _outcome_to_result(self, command: str, outcome: Any) -> dict[str, Any]:
        if outcome.success:
            data: dict[str, Any] = {}
            if command == "task_submit_completion" and outcome.data is not None:
                claim: ClaimRecord = outcome.data["claim"]
                data["claim"] = self._claim_to_payload(claim).model_dump(mode="json")
            elif command == "task_verify" and outcome.data is not None:
                verify_claim: ClaimRecord = outcome.data["claim"]
                data["claim"] = self._claim_to_payload(verify_claim).model_dump(mode="json")
                data["task_status"] = outcome.data["task_status"].value
            return {"success": True, "data": data}
        if outcome.denial is not None:
            gaps = TaskVerificationGapsPayload.model_validate(
                outcome.denial.model_dump(mode="json")
            )
            return {
                "success": False,
                "error": outcome.error or "verification gaps",
                "data": {"gaps": gaps.model_dump(mode="json")},
            }
        return {"success": False, "error": outcome.error or "command denied"}

    # ─── 内核记录 → wire 载荷 ───

    def _task_to_payload(self, task: TaskRecord) -> TaskInfoPayload:
        return TaskInfoPayload(
            task_id=task.task_id,
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=TaskStatus(task.status.value),
            metadata=task.metadata,
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat(),
            verification=None
            if task.verification is None
            else {
                "evidence_min": task.verification.evidence_min,
                "evidence_kinds": task.verification.evidence_kinds,
                "checks": task.verification.checks,
                "approver": task.verification.approver,
            },
        )

    def _claim_to_payload(
        self,
        claim: ClaimRecord,
        *,
        evidence: list[TaskEvidencePayload] | None = None,
    ) -> TaskClaimPayload:
        return TaskClaimPayload(
            claim_id=claim.claim_id,
            task_id=claim.task_id,
            claimant_type=ClaimantType(claim.claimant_type.value),
            claimant_id=claim.claimant_id,
            claimant_name=claim.claimant_name,
            note=claim.note,
            evidence=evidence or [],
            state=claim.state.value,  # type: ignore[arg-type]
            checks=[
                {"checker": c.checker, "passed": c.passed, "detail": c.detail} for c in claim.checks
            ],
            verdict_by=claim.verdict_by,
            verdict_at=claim.verdict_at.isoformat() if claim.verdict_at else None,
            verdict_reason=claim.verdict_reason,
            provenance=claim.provenance.model_dump() if claim.provenance else None,
            created_at=claim.created_at.isoformat(),
        )

    def _dump_to_payload(self, dump: dict[str, Any]) -> TaskDumpResultPayload:
        """kernel.dump 输出 → wire 载荷（claims 内嵌 evidence 与 evidence 列表并存）。"""

        tasks = [self._task_from_dict(t) for t in dump["tasks"]]
        claims = [self._claim_from_dict(c) for c in dump["claims"]]
        by_id: dict[str, EvidenceRecord] = {
            e["evidence_id"]: self._evidence_from_dict(e) for e in dump["evidence"]
        }
        claim_payloads = [
            self._claim_to_payload(
                c,
                evidence=[
                    TaskEvidencePayload(
                        evidence_id=by_id[eid].evidence_id,
                        kind=by_id[eid].kind,
                        ref=by_id[eid].ref,
                        digest=by_id[eid].digest,
                        payload=by_id[eid].payload,
                        created_by=by_id[eid].created_by,
                        created_at=by_id[eid].created_at.isoformat(),
                    )
                    for eid in c.evidence_ids
                    if eid in by_id
                ],
            )
            for c in claims
        ]
        evidence_payloads = [
            TaskEvidencePayload(
                evidence_id=by_id[eid].evidence_id,
                kind=by_id[eid].kind,
                ref=by_id[eid].ref,
                digest=by_id[eid].digest,
                payload=by_id[eid].payload,
                created_by=by_id[eid].created_by,
                created_at=by_id[eid].created_at.isoformat(),
            )
            for eid in sorted(by_id)
        ]
        return TaskDumpResultPayload(
            tasks=[self._task_to_payload(t) for t in tasks],
            claims=claim_payloads,
            evidence=evidence_payloads,
        )

    # ─── dump dict → 内核记录（复用 _task/_claim_to_payload）───

    def _task_from_dict(self, data: dict[str, Any]) -> TaskRecord:
        from ghrah.taskstore.models import Verification

        verification = None
        if data.get("verification") is not None:
            verification = Verification.model_validate(data["verification"])
        return TaskRecord(
            task_id=data["task_id"],
            project_id=data["project_id"],
            seq=data["seq"],
            title=data["title"],
            description=data["description"],
            status=data["status"],  # type: ignore[arg-type]
            acceptance=data.get("acceptance"),
            metadata=data.get("metadata") or {},
            verification=verification,
            version=data["version"],
            created_at=data["created_at"],  # type: ignore[arg-type]
            updated_at=data["updated_at"],  # type: ignore[arg-type]
            deleted_at=data.get("deleted_at"),
        )

    def _claim_from_dict(self, data: dict[str, Any]) -> ClaimRecord:
        from ghrah.taskstore.models import CheckOutcome, Provenance

        provenance = (
            Provenance.model_validate(data["provenance"]) if data.get("provenance") else None
        )
        return ClaimRecord(
            claim_id=data["claim_id"],
            task_id=data["task_id"],
            claimant_type=data["claimant_type"],  # type: ignore[arg-type]
            claimant_id=data["claimant_id"],
            claimant_name=data.get("claimant_name"),
            note=data.get("note"),
            evidence_ids=data.get("evidence_ids") or [],
            state=data["state"],  # type: ignore[arg-type]
            checks=[CheckOutcome.model_validate(c) for c in data.get("checks") or []],
            verdict_by=data.get("verdict_by"),
            verdict_at=data.get("verdict_at"),  # type: ignore[arg-type]
            verdict_reason=data.get("verdict_reason"),
            provenance=provenance,
            version=data["version"],
            created_at=data["created_at"],  # type: ignore[arg-type]
        )

    def _evidence_from_dict(self, data: dict[str, Any]) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=data["evidence_id"],
            kind=data["kind"],
            ref=data["ref"],
            digest=data.get("digest"),
            payload=data.get("payload") or {},
            created_by=data.get("created_by"),
            created_at=data["created_at"],  # type: ignore[arg-type]
        )
