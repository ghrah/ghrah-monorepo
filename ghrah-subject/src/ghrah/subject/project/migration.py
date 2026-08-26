"""Legacy global persistence migration into exclusive Project Roots."""

from __future__ import annotations

import asyncio
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ghrah.subject.project.models import ProjectRecord
from ghrah.subject.project.paths import ProjectPaths

__all__ = [
    "ActionChainMigrationReport",
    "backup_legacy_database",
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
        available = {
            row[0] for row in source.execute("SELECT agent_name FROM agents").fetchall()
        }
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
                    f"SELECT DISTINCT run_id FROM agents "
                    f"WHERE agent_name IN ({placeholders})",
                    tuple(names),
                ).fetchall()
            ]
            if dry_run:
                count = len(run_ids)
                for table in _AGENT_TABLES:
                    if _table_exists(source, table):
                        count += source.execute(
                            f"SELECT COUNT(*) FROM {table} "
                            f"WHERE agent_name IN ({placeholders})",
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


def _backup_sync(source_path: Path) -> Path | None:
    if not source_path.is_file():
        return None
    backup_path = source_path.with_name(
        f"{source_path.name}.pre-project-migration.bak"
    )
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
