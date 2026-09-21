# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""sqlite 权威：tasks / claims / evidence 三表 + schema 版本表。

零钟读：本模块不调用 datetime.now() / uuid4()——created_at / updated_at /
claim_id / evidence_id / seq 全部由调用方（边界层）显式传入；seq 仅在锁内做
MAX(seq)+1 的读取-写入。这是重放逐位一致的硬前提。

范式沿用本仓 store：独立 aiosqlite 连接 + WAL + 幂等 DDL + version 乐观锁 +
deleted_at 软删 + asyncio.Lock。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from ghrah.taskstore.errors import ConcurrentModificationError
from ghrah.taskstore.models import ClaimRecord, EvidenceRecord, TaskRecord

__all__ = ["TaskStore"]

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id      TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL DEFAULT '',
    seq          INTEGER NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL,
    acceptance   TEXT,
    metadata     TEXT NOT NULL DEFAULT '{}',
    verification TEXT,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_project_seq ON tasks(project_id, seq);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_deleted ON tasks(deleted_at);
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    ref         TEXT NOT NULL,
    digest      TEXT,
    payload     TEXT NOT NULL DEFAULT '{}',
    created_by  TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE(kind, ref, digest)
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL,
    claimant_type TEXT NOT NULL DEFAULT 'agent',
    claimant_id   TEXT NOT NULL,
    claimant_name TEXT,
    note          TEXT,
    evidence_ids  TEXT NOT NULL DEFAULT '[]',
    state         TEXT NOT NULL,
    checks        TEXT NOT NULL DEFAULT '[]',
    verdict_by    TEXT,
    verdict_at    TEXT,
    verdict_reason TEXT,
    provenance    TEXT,
    version       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_task ON claims(task_id);
CREATE INDEX IF NOT EXISTS idx_claims_state ON claims(state);
CREATE INDEX IF NOT EXISTS idx_claims_claimant ON claims(claimant_id);
"""

_TASK_COLUMNS = (
    "task_id",
    "project_id",
    "seq",
    "title",
    "description",
    "status",
    "acceptance",
    "metadata",
    "verification",
    "version",
    "created_at",
    "updated_at",
    "deleted_at",
)
_TASK_JSON_COLUMNS = ("metadata", "verification")

_CLAIM_COLUMNS = (
    "claim_id",
    "task_id",
    "claimant_type",
    "claimant_id",
    "claimant_name",
    "note",
    "evidence_ids",
    "state",
    "checks",
    "verdict_by",
    "verdict_at",
    "verdict_reason",
    "provenance",
    "version",
    "created_at",
)
_CLAIM_JSON_COLUMNS = ("evidence_ids", "checks", "provenance")

_EVIDENCE_COLUMNS = (
    "evidence_id",
    "kind",
    "ref",
    "digest",
    "payload",
    "created_by",
    "created_at",
)
_EVIDENCE_JSON_COLUMNS = ("payload",)


def _dt(value: datetime | str | None) -> str | None:
    """datetime → ISO 字符串（None 透传）。"""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _task_to_row(record: TaskRecord) -> dict[str, Any]:
    d = record.model_dump(mode="json")
    for col in _TASK_JSON_COLUMNS:
        d[col] = json.dumps(d[col]) if d[col] is not None else None
    return d


def _row_to_task(row: aiosqlite.Row) -> TaskRecord:
    d = dict(row)
    for col in _TASK_JSON_COLUMNS:
        if d[col] is not None:
            d[col] = json.loads(d[col])
    return TaskRecord.model_validate(d)


def _claim_to_row(record: ClaimRecord) -> dict[str, Any]:
    d = record.model_dump(mode="json")
    for col in _CLAIM_JSON_COLUMNS:
        d[col] = json.dumps(d[col]) if d[col] is not None else None
    return d


def _row_to_claim(row: aiosqlite.Row) -> ClaimRecord:
    d = dict(row)
    for col in _CLAIM_JSON_COLUMNS:
        if d[col] is not None:
            d[col] = json.loads(d[col])
    return ClaimRecord.model_validate(d)


def _evidence_to_row(record: EvidenceRecord) -> dict[str, Any]:
    d = record.model_dump(mode="json")
    for col in _EVIDENCE_JSON_COLUMNS:
        d[col] = json.dumps(d[col]) if d[col] is not None else None
    return d


def _row_to_evidence(row: aiosqlite.Row) -> EvidenceRecord:
    d = dict(row)
    for col in _EVIDENCE_JSON_COLUMNS:
        if d[col] is not None:
            d[col] = json.loads(d[col])
    return EvidenceRecord.model_validate(d)


class TaskStore:
    """任务归因内核的 sqlite 权威（三表唯一真相源）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # ─── 连接管理 ───

    async def start(self) -> None:
        async with self._lock:
            if self._db is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            db = await aiosqlite.connect(str(self._db_path), isolation_level=None)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(_DDL)
            cursor = await db.execute("SELECT COUNT(*) FROM schema_version")
            row = await cursor.fetchone()
            if row is None or int(row[0]) == 0:
                await db.execute("INSERT INTO schema_version VALUES (?)", (_SCHEMA_VERSION,))
            self._db = db
        logger.debug("taskstore started (db=%s)", self._db_path)

    async def stop(self) -> None:
        async with self._lock:
            db = self._db
            if db is None:
                return
            self._db = None
            await db.close()
        logger.debug("taskstore stopped (db=%s)", self._db_path)

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("TaskStore not started. Call start() first.")
        return self._db

    # ─── tasks ───

    async def next_seq(self, project_id: str) -> int:
        """分配项目内自增 seq（MAX(seq)+1，锁内）。"""

        async with self._lock:
            db = self._require_db()
            cursor = await db.execute(
                "SELECT MAX(seq) FROM tasks WHERE project_id = ?", (project_id,)
            )
            row = await cursor.fetchone()
            return (int(row[0]) if row is not None and row[0] is not None else 0) + 1

    async def insert_task(self, task: TaskRecord) -> None:
        """插入新 task（全字段由边界层构造，含 seq）。"""

        async with self._lock:
            db = self._require_db()
            row = _task_to_row(task)
            placeholders = ", ".join(["?"] * len(_TASK_COLUMNS))
            cols = ", ".join(_TASK_COLUMNS)
            await db.execute(
                f"INSERT INTO tasks ({cols}) VALUES ({placeholders})",  # noqa: S608
                tuple(row[c] for c in _TASK_COLUMNS),
            )

    async def update_task(
        self,
        task_id: str,
        *,
        expected_version: int | None,
        mutator: Callable[[TaskRecord], TaskRecord],
    ) -> TaskRecord | None:
        """读出 → 校验 expected_version → 应用 mutator → version+1 → 写回。

        Raises:
            ConcurrentModificationError: expected_version 非空且与当前 version 不匹配。
        """

        async with self._lock:
            db = self._require_db()
            cursor = await db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = await cursor.fetchone()
            if row is None:
                return None
            current = _row_to_task(row)
            if expected_version is not None and current.version != expected_version:
                raise ConcurrentModificationError(
                    f"Task {task_id} modified: expected version {expected_version}, "
                    f"got {current.version}"
                )
            updated = mutator(current)
            updated.version = current.version + 1
            new_row = _task_to_row(updated)
            placeholders = ", ".join([f"{c} = ?" for c in _TASK_COLUMNS])
            await db.execute(
                f"UPDATE tasks SET {placeholders} WHERE task_id = ?",  # noqa: S608
                tuple(new_row[c] for c in _TASK_COLUMNS) + (task_id,),
            )
            return updated

    async def soft_delete_task(self, task_id: str, *, deleted_at: datetime) -> bool:
        """设 deleted_at（由边界层取钟传入），version 自增；返回是否命中。"""

        async with self._lock:
            db = self._require_db()
            cursor = await db.execute(
                "UPDATE tasks SET deleted_at = ?, version = version + 1 "
                "WHERE task_id = ? AND deleted_at IS NULL",
                (deleted_at.isoformat(), task_id),
            )
            return cursor.rowcount > 0

    async def get_task(self, task_id: str, *, include_deleted: bool = False) -> TaskRecord | None:
        async with self._lock:
            db = self._require_db()
            query = "SELECT * FROM tasks WHERE task_id = ?"
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            cursor = await db.execute(query, (task_id,))
            row = await cursor.fetchone()
            return _row_to_task(row) if row is not None else None

    async def list_tasks(
        self,
        *,
        project_id: str | None = None,
        include_deleted: bool = False,
        limit: int | None = None,
    ) -> list[TaskRecord]:
        """列出 task；project_id 过滤，默认排软删，按 seq 升序稳定输出。"""

        async with self._lock:
            db = self._require_db()
            clauses: list[str] = []
            params: list[Any] = []
            if project_id is not None:
                clauses.append("project_id = ?")
                params.append(project_id)
            if not include_deleted:
                clauses.append("deleted_at IS NULL")
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            query = f"SELECT * FROM tasks {where} ORDER BY project_id, seq"  # noqa: S608
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            cursor = await db.execute(query, tuple(params))
            return [_row_to_task(r) for r in await cursor.fetchall()]

    # ─── evidence ───

    async def upsert_evidence(self, evidence: EvidenceRecord) -> tuple[EvidenceRecord, bool]:
        """按 (kind, ref, digest) upsert：命中则复用首写记录（created_at/created_by
        以首次写入为准），未命中插入新行。

        Returns:
            (记录, 是否新插入)。
        """

        async with self._lock:
            db = self._require_db()
            cursor = await db.execute(
                "SELECT * FROM evidence WHERE kind = ? AND ref = ? AND "
                "(? IS NULL AND digest IS NULL OR digest = ?)",
                (evidence.kind, evidence.ref, evidence.digest, evidence.digest),
            )
            row = await cursor.fetchone()
            if row is not None:
                return _row_to_evidence(row), False
            new_row = _evidence_to_row(evidence)
            placeholders = ", ".join(["?"] * len(_EVIDENCE_COLUMNS))
            cols = ", ".join(_EVIDENCE_COLUMNS)
            await db.execute(
                f"INSERT INTO evidence ({cols}) VALUES ({placeholders})",  # noqa: S608
                tuple(new_row[c] for c in _EVIDENCE_COLUMNS),
            )
            return evidence, True

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        async with self._lock:
            db = self._require_db()
            cursor = await db.execute(
                "SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)
            )
            row = await cursor.fetchone()
            return _row_to_evidence(row) if row is not None else None

    async def list_evidence_by_ids(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        """按 id 清单取 evidence（保持清单序；未知 id 静默跳过）。"""

        if not evidence_ids:
            return []
        async with self._lock:
            db = self._require_db()
            placeholders = ", ".join(["?"] * len(evidence_ids))
            cursor = await db.execute(
                f"SELECT * FROM evidence WHERE evidence_id IN ({placeholders})",  # noqa: S608
                tuple(evidence_ids),
            )
            rows = {row["evidence_id"]: row for row in await cursor.fetchall()}
            return [_row_to_evidence(rows[eid]) for eid in evidence_ids if eid in rows]

    # ─── claims ───

    async def insert_claim(self, claim: ClaimRecord) -> None:
        async with self._lock:
            db = self._require_db()
            row = _claim_to_row(claim)
            placeholders = ", ".join(["?"] * len(_CLAIM_COLUMNS))
            cols = ", ".join(_CLAIM_COLUMNS)
            await db.execute(
                f"INSERT INTO claims ({cols}) VALUES ({placeholders})",  # noqa: S608
                tuple(row[c] for c in _CLAIM_COLUMNS),
            )

    async def update_claim(
        self,
        claim_id: str,
        *,
        expected_version: int | None,
        mutator: Callable[[ClaimRecord], ClaimRecord],
    ) -> ClaimRecord | None:
        """读出 → 校验 expected_version → 应用 mutator → version+1 → 写回。"""

        async with self._lock:
            db = self._require_db()
            cursor = await db.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,))
            row = await cursor.fetchone()
            if row is None:
                return None
            current = _row_to_claim(row)
            if expected_version is not None and current.version != expected_version:
                raise ConcurrentModificationError(
                    f"Claim {claim_id} modified: expected version {expected_version}, "
                    f"got {current.version}"
                )
            updated = mutator(current)
            updated.version = current.version + 1
            new_row = _claim_to_row(updated)
            placeholders = ", ".join([f"{c} = ?" for c in _CLAIM_COLUMNS])
            await db.execute(
                f"UPDATE claims SET {placeholders} WHERE claim_id = ?",  # noqa: S608
                tuple(new_row[c] for c in _CLAIM_COLUMNS) + (claim_id,),
            )
            return updated

    async def get_claim(self, claim_id: str) -> ClaimRecord | None:
        async with self._lock:
            db = self._require_db()
            cursor = await db.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,))
            row = await cursor.fetchone()
            return _row_to_claim(row) if row is not None else None

    async def list_claims(
        self,
        *,
        task_id: str | None = None,
        claimant_id: str | None = None,
        state: str | list[str] | None = None,
        limit: int = 100,
    ) -> list[ClaimRecord]:
        """列出 claim；动态过滤，按 created_at + claim_id 稳定排序。"""

        async with self._lock:
            db = self._require_db()
            clauses: list[str] = []
            params: list[Any] = []
            if task_id is not None:
                clauses.append("task_id = ?")
                params.append(task_id)
            if claimant_id is not None:
                clauses.append("claimant_id = ?")
                params.append(claimant_id)
            if state is not None:
                states = [state] if isinstance(state, str) else list(state)
                placeholders = ", ".join(["?"] * len(states))
                clauses.append(f"state IN ({placeholders})")
                params.extend(states)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            cursor = await db.execute(
                f"SELECT * FROM claims {where} ORDER BY created_at, claim_id LIMIT ?",  # noqa: S608
                tuple(params) + (limit,),
            )
            return [_row_to_claim(r) for r in await cursor.fetchall()]

    # ─── dump（D18②：limit 仅限 tasks，claims/evidence 随所选 tasks 收敛）───

    async def dump(
        self,
        *,
        project_id: str | None = None,
        include_deleted: bool = False,
        limit: int | None = None,
    ) -> tuple[list[TaskRecord], list[ClaimRecord], list[EvidenceRecord]]:
        """全量读：tasks（可 limit）→ 其 claims → 这些 claims 的 evidence。"""

        tasks = await self.list_tasks(
            project_id=project_id, include_deleted=include_deleted, limit=limit
        )
        task_ids = [t.task_id for t in tasks]
        if not task_ids:
            return tasks, [], []
        claims = await self._claims_by_task_ids(task_ids)
        evidence_ids = sorted({eid for claim in claims for eid in claim.evidence_ids})
        evidence = await self.list_evidence_by_ids(evidence_ids)
        return tasks, claims, evidence

    async def _claims_by_task_ids(self, task_ids: list[str]) -> list[ClaimRecord]:
        async with self._lock:
            db = self._require_db()
            placeholders = ", ".join(["?"] * len(task_ids))
            cursor = await db.execute(
                f"SELECT * FROM claims WHERE task_id IN ({placeholders}) "  # noqa: S608
                "ORDER BY created_at, claim_id",
                tuple(task_ids),
            )
            return [_row_to_claim(r) for r in await cursor.fetchall()]
