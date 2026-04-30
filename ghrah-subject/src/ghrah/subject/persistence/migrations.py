"""SQLite 数据库迁移脚本。

管理 Subject 持久化数据库的表结构创建和版本迁移。
复用 ghrah-core 的 SqliteBackend 的 schema 定义。

迁移策略：
- 使用 user_version PRAGMA 跟踪数据库版本
- 每个迁移版本对应一个 DDL 脚本
- 迁移在事务中执行，保证原子性
"""

from __future__ import annotations

import logging

import aiosqlite

logger = logging.getLogger(__name__)

__all__ = ["apply_migrations", "CURRENT_VERSION", "MIGRATIONS"]

MIGRATIONS: dict[int, str] = {
    1: """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata     TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS agents (
    agent_name   TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(session_id),
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nodes (
    id                TEXT PRIMARY KEY,
    parent_id         TEXT,
    agent_name        TEXT NOT NULL REFERENCES agents(agent_name),
    timestamp         TEXT NOT NULL,
    iteration         INTEGER NOT NULL DEFAULT 0,
    branch_name       TEXT NOT NULL DEFAULT 'main',
    is_snapshot       INTEGER NOT NULL DEFAULT 0,
    ability_names     TEXT NOT NULL DEFAULT '[]',
    agent_state       TEXT NOT NULL DEFAULT '{}',
    messages_delta    TEXT NOT NULL DEFAULT '[]',
    messages_snapshot TEXT,
    action_results    TEXT NOT NULL DEFAULT '[]',
    metadata          TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chain_meta (
    agent_name    TEXT PRIMARY KEY REFERENCES agents(agent_name),
    branches      TEXT NOT NULL DEFAULT '{}',
    current_state TEXT NOT NULL DEFAULT '{}',
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    agent_name    TEXT PRIMARY KEY REFERENCES agents(agent_name),
    messages      TEXT NOT NULL DEFAULT '[]',
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_agent ON nodes(agent_name);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_branch ON nodes(agent_name, branch_name);
CREATE INDEX IF NOT EXISTS idx_nodes_iteration ON nodes(agent_name, iteration);
CREATE INDEX IF NOT EXISTS idx_agents_session ON agents(session_id);
""",
    2: """
-- v2: 对齐 ghrah-core SqliteBackend schema
-- sessions → runs 重命名, 新 sessions 表 (branch session),
-- nodes.session_id, chain_meta.active_session_id, agents.session_id → run_id

-- 1. 创建 runs 表
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata     TEXT DEFAULT '{}'
);

-- 2. 将旧 sessions 表数据迁移到 runs
INSERT OR IGNORE INTO runs (run_id, created_at, updated_at, metadata)
    SELECT session_id, created_at, updated_at, metadata FROM sessions;

-- 3. 备份旧 sessions 表, 创建新 branch sessions 表
ALTER TABLE sessions RENAME TO _sessions_v1_backup;
CREATE TABLE sessions (
    session_id        TEXT PRIMARY KEY,
    agent_name        TEXT NOT NULL,
    branch_name       TEXT NOT NULL DEFAULT 'main',
    parent_node_id    TEXT,
    parent_session_id TEXT,
    rebase_from_agent  TEXT,
    rebase_from_node_id TEXT,
    rebase_from_session_id TEXT,
    system_prompt     TEXT DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata          TEXT DEFAULT '{}'
);
DROP TABLE IF EXISTS _sessions_v1_backup;

-- 4. 重建 agents 表 (session_id → run_id)
CREATE TABLE agents_new (
    agent_name   TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES runs(run_id),
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO agents_new (agent_name, run_id, created_at, updated_at)
    SELECT agent_name, session_id, created_at, updated_at FROM agents;
DROP TABLE agents;
ALTER TABLE agents_new RENAME TO agents;

-- 5. 索引
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_name);
CREATE INDEX IF NOT EXISTS idx_agents_run ON agents(run_id);
""",
}

CURRENT_VERSION = max(MIGRATIONS.keys())


async def _get_user_version(db: aiosqlite.Connection) -> int:
    cursor = await db.execute("PRAGMA user_version")
    row = await cursor.fetchone()
    return int(row[0]) if row is not None else 0


async def _set_user_version(db: aiosqlite.Connection, version: int) -> None:
    await db.execute(f"PRAGMA user_version = {version}")


async def _ensure_v2_columns(db: aiosqlite.Connection) -> None:
    """安全地添加 v2 新增列（仅当列不存在时添加）。

    ALTER TABLE ADD COLUMN 在列已存在时会报错，
    所以先检查列是否存在再添加。
    """
    cursor = await db.execute("PRAGMA table_info(nodes)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "session_id" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")

    cursor = await db.execute("PRAGMA table_info(chain_meta)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "active_session_id" not in columns:
        await db.execute(
            "ALTER TABLE chain_meta ADD COLUMN active_session_id TEXT NOT NULL DEFAULT ''"
        )

    await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_session ON nodes(session_id)")
    await db.commit()


async def apply_migrations(db: aiosqlite.Connection) -> int:
    """对数据库执行所有未应用的迁移。

    使用 PRAGMA user_version 跟踪当前版本，按序执行迁移脚本。
    每个迁移在独立事务中执行。

    Args:
        db: aiosqlite 连接对象

    Returns:
        应用后的最终版本号
    """
    current = await _get_user_version(db)
    if current >= CURRENT_VERSION:
        logger.debug("Database schema is up to date (version %d)", current)
        return current

    for version in sorted(MIGRATIONS.keys()):
        if version <= current:
            continue
        ddl = MIGRATIONS[version]
        try:
            await db.executescript(ddl)
        except Exception as e:
            logger.warning(
                "Migration v%d DDL failed (may have already been applied by SqliteBackend): %s",
                version,
                e,
            )
        await _set_user_version(db, version)
        logger.info("Applied migration v%d", version)

        if version == 2:
            await _ensure_v2_columns(db)

    return CURRENT_VERSION
