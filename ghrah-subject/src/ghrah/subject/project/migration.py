"""Legacy global persistence migration into exclusive Project Roots."""

from __future__ import annotations

import asyncio
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ghrah.subject.project.models import ProjectRecord
from ghrah.subject.project.paths import ProjectPaths

__all__ = [
    "ActionChainMigrationReport",
    "AgentIdentityMigrationReport",
    "backup_legacy_database",
    "mark_migration_completed",
    "migration_completed",
    "migrate_project_agent_ids",
    "migrate_legacy_action_chains",
]

_AGENT_TABLES = ("agents", "sessions", "nodes", "chain_meta", "messages")


@dataclass
class ActionChainMigrationReport:
    """Auditable result; ambiguous agent ownership is always reported and skipped."""

    dry_run: bool
    backup_path: str | None = None
    migrated_rows: dict[str, int] = field(default_factory=dict)
    ambiguous_agents: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(self.migrated_rows.values())


@dataclass
class AgentIdentityMigrationReport:
    """旧 name-key checkpoint → UUID-key 的可审计迁移结果。"""

    project_id: str
    agent_ids: dict[tuple[str, str], str] = field(default_factory=dict)
    ambiguous_names: list[str] = field(default_factory=list)
    migrated_rows: int = 0
    backup_path: str | None = None


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _copy_schema(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    rows = source.execute(
        "SELECT type, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND type IN ('table', 'index') "
        "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"
    ).fetchall()
    for _kind, sql in rows:
        statement = sql
        if "IF NOT EXISTS" not in statement.upper():
            statement = statement.replace(
                "CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1
            ).replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
        target.execute(statement)


def _insert_rows(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    table: str,
    where: str,
    params: tuple[object, ...],
) -> int:
    if not _table_exists(source, table):
        return 0
    columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
    rows = source.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE {where}", params
    ).fetchall()
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    before = target.total_changes
    target.executemany(
        f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        rows,
    )
    return target.total_changes - before


def _migrate_sync(
    legacy_path: Path,
    projects: list[ProjectRecord],
    dry_run: bool,
) -> ActionChainMigrationReport:
    report = ActionChainMigrationReport(dry_run=dry_run)
    if not legacy_path.is_file():
        return report

    ownership = Counter(agent.name for project in projects for agent in project.agents)
    report.ambiguous_agents = sorted(name for name, count in ownership.items() if count > 1)

    source = sqlite3.connect(legacy_path)
    try:
        if not _table_exists(source, "agents"):
            return report
        available = {row[0] for row in source.execute("SELECT agent_name FROM agents").fetchall()}
        candidates = {
            agent.name
            for project in projects
            for agent in project.agents
            if ownership[agent.name] == 1 and agent.name in available
        }
        if not candidates:
            return report

        backup_path = legacy_path.with_name(f"{legacy_path.name}.pre-project-migration.bak")
        report.backup_path = str(backup_path)
        if not dry_run and not backup_path.exists():
            backup = sqlite3.connect(backup_path)
            try:
                source.backup(backup)
            finally:
                backup.close()

        for project in projects:
            names = sorted(
                agent.name
                for agent in project.agents
                if agent.name in candidates and ownership[agent.name] == 1
            )
            if not names:
                continue
            placeholders = ", ".join("?" for _ in names)
            run_ids = [
                row[0]
                for row in source.execute(
                    f"SELECT DISTINCT run_id FROM agents WHERE agent_name IN ({placeholders})",
                    tuple(names),
                ).fetchall()
            ]
            if dry_run:
                count = len(run_ids)
                for table in _AGENT_TABLES:
                    if _table_exists(source, table):
                        count += source.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE agent_name IN ({placeholders})",
                            tuple(names),
                        ).fetchone()[0]
                report.migrated_rows[project.project_id] = count
                continue

            target_path = ProjectPaths.from_locator(
                project.project_root_locator
            ).action_chain_db_path
            if target_path.resolve() == legacy_path.resolve():
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target = sqlite3.connect(target_path)
            try:
                _copy_schema(source, target)
                copied = 0
                if run_ids:
                    run_placeholders = ", ".join("?" for _ in run_ids)
                    copied += _insert_rows(
                        source,
                        target,
                        "runs",
                        f"run_id IN ({run_placeholders})",
                        tuple(run_ids),
                    )
                for table in _AGENT_TABLES:
                    copied += _insert_rows(
                        source,
                        target,
                        table,
                        f"agent_name IN ({placeholders})",
                        tuple(names),
                    )
                target.commit()
                report.migrated_rows[project.project_id] = copied
            finally:
                target.close()
    finally:
        source.close()
    return report


async def migrate_legacy_action_chains(
    legacy_path: str | Path,
    projects: list[ProjectRecord],
    *,
    dry_run: bool = False,
) -> ActionChainMigrationReport:
    """Copy uniquely owned development data; retain the source as rollback evidence."""
    return await asyncio.to_thread(_migrate_sync, Path(legacy_path), projects, dry_run)


def _stable_legacy_agent_id(project_id: str, cluster_id: str, name: str) -> str:
    """为可唯一解析的旧 Agent 生成可重试的稳定 UUID。"""
    return uuid5(
        NAMESPACE_URL,
        f"ghrah-agent:{project_id}:{cluster_id}:{name}",
    ).hex


def _migrate_project_agent_ids_sync(
    project: ProjectRecord,
) -> AgentIdentityMigrationReport:
    report = AgentIdentityMigrationReport(project_id=project.project_id)
    ownership = Counter(agent.name for agent in project.agents)
    report.ambiguous_names = sorted(
        name
        for name, count in ownership.items()
        if count > 1 and any(a.name == name and not a.agent_id for a in project.agents)
    )
    target_ids: dict[tuple[str, str], str] = {}
    for agent in project.agents:
        if ownership[agent.name] != 1:
            continue
        target_id = agent.agent_id or _stable_legacy_agent_id(
            project.project_id, agent.cluster_id, agent.name
        )
        target_ids[(agent.cluster_id, agent.name)] = target_id
        if not agent.agent_id:
            report.agent_ids[(agent.cluster_id, agent.name)] = target_id
    if not target_ids:
        return report

    db_path = ProjectPaths.from_locator(project.project_root_locator).action_chain_db_path
    if not db_path.is_file():
        return report
    db = sqlite3.connect(db_path)
    try:
        if not _table_exists(db, "agents"):
            return report
        available = {str(row[0]) for row in db.execute("SELECT agent_name FROM agents").fetchall()}
        to_rekey = {
            name: agent_id
            for (_cluster_id, name), agent_id in target_ids.items()
            if name in available and agent_id not in available
        }
        if not to_rekey:
            return report

        backup_path = db_path.with_name(f"{db_path.name}.pre-agent-id-migration.bak")
        report.backup_path = str(backup_path)
        if not backup_path.exists():
            backup = sqlite3.connect(backup_path)
            try:
                db.backup(backup)
            finally:
                backup.close()

        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("BEGIN IMMEDIATE")
        try:
            for old_name, agent_id in to_rekey.items():
                for table in ("sessions", "nodes", "chain_meta", "messages", "agents"):
                    if not _table_exists(db, table):
                        continue
                    before = db.total_changes
                    db.execute(
                        f"UPDATE {table} SET agent_name = ? WHERE agent_name = ?",  # noqa: S608
                        (agent_id, old_name),
                    )
                    report.migrated_rows += db.total_changes - before
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("PRAGMA foreign_keys=ON")
    finally:
        db.close()
    return report


async def migrate_project_agent_ids(
    project: ProjectRecord,
) -> AgentIdentityMigrationReport:
    """迁移单 Project 内可唯一解析的旧 Agent 身份与 checkpoint 外键。"""
    return await asyncio.to_thread(_migrate_project_agent_ids_sync, project)


def _backup_sync(source_path: Path) -> Path | None:
    if not source_path.is_file():
        return None
    backup_path = source_path.with_name(f"{source_path.name}.pre-project-migration.bak")
    if backup_path.exists():
        return backup_path
    source = sqlite3.connect(source_path)
    backup = sqlite3.connect(backup_path)
    try:
        source.backup(backup)
    finally:
        backup.close()
        source.close()
    return backup_path


async def backup_legacy_database(source_path: str | Path) -> Path | None:
    """Create a consistent, one-time SQLite backup before destructive splits."""
    return await asyncio.to_thread(_backup_sync, Path(source_path))


_MARKER_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS migration_markers ("
    "key TEXT PRIMARY KEY, completed_at TEXT NOT NULL)"
)


async def migration_completed(db_path: str | Path, key: str) -> bool:
    """一次性迁移标记：key 是否已标记完成（标记表建在 catalog 库内）。"""

    def _check() -> bool:
        with sqlite3.connect(str(db_path)) as db:
            db.execute(_MARKER_TABLE_SQL)
            row = db.execute("SELECT 1 FROM migration_markers WHERE key = ?", (key,)).fetchone()
            return row is not None

    return await asyncio.to_thread(_check)


async def mark_migration_completed(db_path: str | Path, key: str) -> None:
    """标记一次性迁移完成（幂等；仅在迁移全量成功后调用）。"""
    from datetime import datetime

    def _mark() -> None:
        with sqlite3.connect(str(db_path)) as db:
            db.execute(_MARKER_TABLE_SQL)
            db.execute(
                "INSERT OR IGNORE INTO migration_markers (key, completed_at) VALUES (?, ?)",
                (key, datetime.now(UTC).isoformat()),
            )
            db.commit()

    await asyncio.to_thread(_mark)
