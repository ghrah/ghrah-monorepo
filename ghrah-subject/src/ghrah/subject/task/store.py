from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from ghrah.subject.task.models import TaskRecord

logger = logging.getLogger(__name__)

__all__ = ["ConcurrentModificationError", "TaskStore"]

# 模块级类型别名：避免实例方法 `list` 遮蔽内置 list 在注解中报 valid-type。
TaskRecordList = list[TaskRecord]


class ConcurrentModificationError(Exception):
    """乐观锁：expected_version 与当前 version 不匹配。"""


_DDL = """
CREATE TABLE IF NOT EXISTS subject_tasks (
    task_id      TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    agent_name   TEXT,
    status       TEXT NOT NULL,
    priority     TEXT NOT NULL,
    parent_id    TEXT,
    dependencies TEXT NOT NULL DEFAULT '[]',
    result       TEXT,
    error        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    started_at   TEXT,
    completed_at TEXT,
    metadata     TEXT NOT NULL DEFAULT '{}',
    version      INTEGER NOT NULL DEFAULT 1,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_subject_tasks_status  ON subject_tasks(status);
CREATE INDEX IF NOT EXISTS idx_subject_tasks_agent   ON subject_tasks(agent_name);
CREATE INDEX IF NOT EXISTS idx_subject_tasks_parent  ON subject_tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_subject_tasks_deleted ON subject_tasks(deleted_at);
"""

_COLUMNS = (
    "task_id",
    "title",
    "description",
    "agent_name",
    "status",
    "priority",
    "parent_id",
    "dependencies",
    "result",
    "error",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
    "metadata",
    "version",
    "deleted_at",
)
_JSON_COLUMNS = ("dependencies", "metadata", "result")
_TERMINAL_STATUSES = ("completed", "failed", "canceled")


def _record_to_row(record: TaskRecord) -> dict[str, Any]:
    """TaskRecord → 列 dict（JSON 字段 json.dumps，其余直存）。"""
    d = record.model_dump(mode="json")
    for col in _JSON_COLUMNS:
        d[col] = json.dumps(d[col])
    return d


def _row_to_record(row: aiosqlite.Row) -> TaskRecord:
    """列 dict → TaskRecord（JSON 字段 json.loads，时间戳经 _coerce_dt 还原）。"""
    d = dict(row)
    for col in _JSON_COLUMNS:
        if d[col] is not None:
            d[col] = json.loads(d[col])
    return TaskRecord.model_validate(d)


class TaskStore:
    """SQLite TaskStore：独立 aiosqlite 连接，幂等 DDL，乐观锁 + 软删。

    拓扑校验（环/可达/邻接）不在此处，集中在 TaskGraphView。store 仅负责持久化 +
    提供视图构造所需的全图读取（list_all_active）+ SQL 快速存在性短路
    （count_dependents/count_children 用于 delete 保护判空）。
    """

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
            # isolation_level=None 启用手动事务控制，避免隐式事务冲突
            db = await aiosqlite.connect(str(self._db_path), isolation_level=None)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(_DDL)
            self._db = db
        logger.debug("TaskStore started (db=%s)", self._db_path)

    async def stop(self) -> None:
        async with self._lock:
            db = self._db
            if db is None:
                return
            self._db = None
            await db.close()
        logger.debug("TaskStore stopped (db=%s)", self._db_path)

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("TaskStore not started. Call start() first.")
        return self._db

    # ─── 写入 ───

    async def upsert(self, task: TaskRecord) -> None:
        """INSERT OR REPLACE（新任务或全量覆盖，version 由调用方控制）。"""
        async with self._lock:
            db = self._require_db()
            row = _record_to_row(task)
            placeholders = ", ".join(["?"] * len(_COLUMNS))
            cols = ", ".join(_COLUMNS)
            await db.execute(
                f"INSERT OR REPLACE INTO subject_tasks ({cols}) VALUES ({placeholders})",  # noqa: S608
                tuple(row[c] for c in _COLUMNS),
            )

    async def update(
        self,
        task_id: str,
        *,
        expected_version: int | None,
        mutator: Callable[[TaskRecord], TaskRecord],
    ) -> TaskRecord | None:
        """读出 → 校验 expected_version → 应用 mutator → version+1 → 写回。

        读 raw 行（不过滤 deleted_at）：乐观锁要求读到行真相。是否改已删任务由
        manager 决定策略，store 不阻拦。

        Raises:
            ConcurrentModificationError: expected_version 非空且与当前 version 不匹配。
        """
        async with self._lock:
            db = self._require_db()
            cursor = await db.execute(
                "SELECT * FROM subject_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            current = _row_to_record(row)
            if expected_version is not None and current.version != expected_version:
                raise ConcurrentModificationError(
                    f"Task {task_id} modified: expected version {expected_version}, "
                    f"got {current.version}"
                )
            updated = mutator(current)
            updated.version = current.version + 1
            new_row = _record_to_row(updated)
            placeholders = ", ".join([f"{c} = ?" for c in _COLUMNS])
            await db.execute(
                f"UPDATE subject_tasks SET {placeholders} WHERE task_id = ?",  # noqa: S608
                tuple(new_row[c] for c in _COLUMNS) + (task_id,),
            )
            return updated

    async def soft_delete(self, task_id: str) -> bool:
        """设 deleted_at = now，version 自增；返回是否命中。

        已软删的任务重复调用返回 False（WHERE deleted_at IS NULL 不再命中）。
        """
        async with self._lock:
            db = self._require_db()
            now = datetime.now(UTC).isoformat()
            cursor = await db.execute(
                "UPDATE subject_tasks SET deleted_at = ?, version = version + 1 "
                "WHERE task_id = ? AND deleted_at IS NULL",
                (now, task_id),
            )
            return cursor.rowcount > 0

    # ─── 读取 ───

    async def get(
        self, task_id: str, *, include_deleted: bool = False
    ) -> TaskRecord | None:
        """按 task_id 取记录；默认排除软删。"""
        async with self._lock:
            db = self._require_db()
            query = "SELECT * FROM subject_tasks WHERE task_id = ?"
            params: list[Any] = [task_id]
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            cursor = await db.execute(query, tuple(params))
            row = await cursor.fetchone()
            return _row_to_record(row) if row is not None else None

    async def exists(self, task_id: str, *, include_deleted: bool = False) -> bool:
        """task_id 是否存在；默认排除软删。"""
        async with self._lock:
            db = self._require_db()
            query = "SELECT 1 FROM subject_tasks WHERE task_id = ?"
            params: list[Any] = [task_id]
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            cursor = await db.execute(query, tuple(params))
            return await cursor.fetchone() is not None

    async def list(
        self,
        *,
        agent_name: str | None = None,
        status: str | None = None,
        parent_id: str | None = None,
        include_terminal: bool = False,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> TaskRecordList:
        """动态 WHERE 拼接过滤；默认排除软删与终态。"""
        async with self._lock:
            db = self._require_db()
            clauses: list[str] = []
            params: list[Any] = []
            if not include_deleted:
                clauses.append("deleted_at IS NULL")
            if agent_name is not None:
                clauses.append("agent_name = ?")
                params.append(agent_name)
            if status is not None:
                clauses.append("status = ?")
                params.append(status)
            if parent_id is not None:
                clauses.append("parent_id = ?")
                params.append(parent_id)
            if not include_terminal:
                placeholders = ", ".join(["?"] * len(_TERMINAL_STATUSES))
                clauses.append(f"status NOT IN ({placeholders})")
                params.extend(_TERMINAL_STATUSES)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            cursor = await db.execute(
                f"SELECT * FROM subject_tasks {where} ORDER BY created_at LIMIT ?",  # noqa: S608
                tuple(params) + (limit,),
            )
            rows = await cursor.fetchall()
            return [_row_to_record(r) for r in rows]

    async def list_all_active(self) -> TaskRecordList:
        """返回所有未软删记录，供 TaskGraphView 构造（环/可达/邻接唯一全图读入口）。"""
        async with self._lock:
            db = self._require_db()
            cursor = await db.execute(
                "SELECT * FROM subject_tasks WHERE deleted_at IS NULL ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            return [_row_to_record(r) for r in rows]

    # ─── SQL 快速存在性短路（delete 保护判空用）───

    async def count_dependents(self, task_id: str) -> int:
        """有多少未软删任务依赖 task_id（反邻接计数）。

        双层防护防子串误判：
        1. SQL LIKE '%"task_id"%' 粗筛（task_id 为 32 位 hex 无引号，
           带引号 LIKE 误判概率极低）
        2. Python json.loads 后精确 in 校验（最终保证）

        仅作 SQL 短路：拓扑精确判定由 manager 经 TaskGraphView.dependents_of 完成。
        """
        async with self._lock:
            db = self._require_db()
            pattern = f'%"{task_id}"%'
            cursor = await db.execute(
                "SELECT dependencies FROM subject_tasks "
                "WHERE dependencies LIKE ? AND deleted_at IS NULL",
                (pattern,),
            )
            rows = await cursor.fetchall()
            count = 0
            for r in rows:
                deps = json.loads(r["dependencies"])
                if task_id in deps:
                    count += 1
            return count

    async def count_children(self, parent_id: str) -> int:
        """parent_id 的未软删直接子任务数（SQL 短路）。"""
        async with self._lock:
            db = self._require_db()
            cursor = await db.execute(
                "SELECT COUNT(*) FROM subject_tasks "
                "WHERE parent_id = ? AND deleted_at IS NULL",
                (parent_id,),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row is not None else 0
