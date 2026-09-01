# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WorkspaceStore：aiosqlite 独立连接，幂等 DDL，CRUD + 软删。

store 持久化 :class:`WorkspaceRecord`，幂等 DDL（同 TaskStore 范式）。

marker 携带 subject_id 用于认领三要素校验，store 同步存储以便重启重建）：

    CREATE TABLE IF NOT EXISTS subject_workspaces (
        workspace_id  TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        provider_type TEXT NOT NULL,
        subject_id    TEXT NOT NULL DEFAULT 'default',
        locator       TEXT NOT NULL UNIQUE,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        deleted_at    TEXT
    );

marker JSON（.ghrah-workspace）三要素校验由 :mod:`ghrah.subject.workspace.marker`
提供：read_marker 解析 workspace_id/provider_type/subject_id；旧格式（一行注释）
不可机读 → None，不自动认领。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from ghrah.subject.workspace.models import WorkspaceRecord

logger = logging.getLogger(__name__)

__all__ = ["WorkspaceStore"]

# 模块级类型别名：避免实例方法 `list` 遮蔽内置 list 在注解中报 valid-type（同 TaskStore）。
WorkspaceRecordList = list[WorkspaceRecord]

# 幂等 DDL（每次 start 执行，IF NOT EXISTS 保证安全）。
_DDL = """
CREATE TABLE IF NOT EXISTS subject_workspaces (
    workspace_id  TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    subject_id    TEXT NOT NULL DEFAULT 'default',
    locator       TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_subject_workspaces_provider
    ON subject_workspaces(provider_type);
CREATE INDEX IF NOT EXISTS idx_subject_workspaces_deleted
    ON subject_workspaces(deleted_at);
"""

_COLUMNS = (
    "workspace_id",
    "name",
    "provider_type",
    "subject_id",
    "locator",
    "created_at",
    "updated_at",
    "deleted_at",
)


class WorkspaceStore:
    """SQLite WorkspaceStore：独立 aiosqlite 连接，幂等 DDL + 软删。

    仅负责持久化与查询；认领三要素校验逻辑不在 store（marker 校验由 marker
    模块 + provider.adopt 完成，store 只存 record 真相）。
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
            db = await aiosqlite.connect(str(self._db_path), isolation_level=None)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(_DDL)
            self._db = db
        logger.debug("WorkspaceStore started (db=%s)", self._db_path)

    async def stop(self) -> None:
        async with self._lock:
            db = self._db
            if db is None:
                return
            self._db = None
            await db.close()
        logger.debug("WorkspaceStore stopped (db=%s)", self._db_path)

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("WorkspaceStore not started. Call start() first.")
        return self._db

    # ─── 写入 ───

    async def upsert(self, record: WorkspaceRecord) -> None:
        """INSERT OR REPLACE（新 workspace 或全量覆盖）。

        locator 唯一约束：若另一记录已占用同一 locator，UNIQUE 冲突由调用方
        （manager）在认领时先行校验，store 不在此处做合并决策。
        """
        async with self._lock:
            db = self._require_db()
            row = _record_to_row(record)
            placeholders = ", ".join(["?"] * len(_COLUMNS))
            cols = ", ".join(_COLUMNS)
            await db.execute(
                f"INSERT OR REPLACE INTO subject_workspaces ({cols}) VALUES ({placeholders})",  # noqa: S608
                tuple(row[c] for c in _COLUMNS),
            )

    async def touch(self, workspace_id: str) -> bool:
        """更新 updated_at = now；返回是否命中（默认排除软删）。"""
        async with self._lock:
            db = self._require_db()
            now = datetime.now(UTC).isoformat()
            cursor = await db.execute(
                "UPDATE subject_workspaces SET updated_at = ? "
                "WHERE workspace_id = ? AND deleted_at IS NULL",
                (now, workspace_id),
            )
            return cursor.rowcount > 0

    async def soft_delete(self, workspace_id: str) -> bool:
        """设 deleted_at = now；已软删重复调用返回 False。"""
        async with self._lock:
            db = self._require_db()
            now = datetime.now(UTC).isoformat()
            cursor = await db.execute(
                "UPDATE subject_workspaces SET deleted_at = ?, updated_at = ? "
                "WHERE workspace_id = ? AND deleted_at IS NULL",
                (now, now, workspace_id),
            )
            return cursor.rowcount > 0

    # ─── 读取 ───

    async def get(
        self, workspace_id: str, *, include_deleted: bool = False
    ) -> WorkspaceRecord | None:
        """按 workspace_id 取记录；默认排除软删。"""
        async with self._lock:
            db = self._require_db()
            query = "SELECT * FROM subject_workspaces WHERE workspace_id = ?"
            params: list[Any] = [workspace_id]
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            cursor = await db.execute(query, tuple(params))
            row = await cursor.fetchone()
            return _row_to_record(row) if row is not None else None

    async def get_by_locator(
        self, locator: str, *, include_deleted: bool = False
    ) -> WorkspaceRecord | None:
        """按 locator 取记录（locator 唯一）；默认排除软删。"""
        async with self._lock:
            db = self._require_db()
            query = "SELECT * FROM subject_workspaces WHERE locator = ?"
            params: list[Any] = [locator]
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            cursor = await db.execute(query, tuple(params))
            row = await cursor.fetchone()
            return _row_to_record(row) if row is not None else None

    async def list(
        self,
        *,
        provider_type: str | None = None,
        subject_id: str | None = None,
        include_deleted: bool = False,
    ) -> WorkspaceRecordList:
        """动态 WHERE 过滤；默认排除软删，按 created_at 排序。"""
        async with self._lock:
            db = self._require_db()
            clauses: list[str] = []
            params: list[Any] = []
            if not include_deleted:
                clauses.append("deleted_at IS NULL")
            if provider_type is not None:
                clauses.append("provider_type = ?")
                params.append(provider_type)
            if subject_id is not None:
                clauses.append("subject_id = ?")
                params.append(subject_id)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            cursor = await db.execute(
                f"SELECT * FROM subject_workspaces {where} ORDER BY created_at",  # noqa: S608
                tuple(params),
            )
            rows = await cursor.fetchall()
            return [_row_to_record(r) for r in rows]

    async def list_all_active(self) -> WorkspaceRecordList:
        """返回所有未软删记录（W5 manager start 重建内存索引用）。"""
        return await self.list(include_deleted=False)


def _record_to_row(record: WorkspaceRecord) -> dict[str, Any]:
    """WorkspaceRecord → 列 dict（时间戳 ISO str，其余直存）。"""
    return {
        "workspace_id": record.workspace_id,
        "name": record.name,
        "provider_type": record.provider_type,
        "subject_id": record.subject_id,
        "locator": record.locator,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None,
    }


def _row_to_record(row: aiosqlite.Row) -> WorkspaceRecord:
    """列 dict → WorkspaceRecord（pydantic _coerce_dt 还原时间戳）。"""
    d = dict(row)
    return WorkspaceRecord.model_validate(d)
