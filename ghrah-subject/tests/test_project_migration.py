from __future__ import annotations

import sqlite3
from pathlib import Path

from ghrah.subject.project.migration import migrate_legacy_action_chains
from ghrah.subject.project.models import AgentSpec, make_project_record
from ghrah.subject.project.paths import ProjectPaths
from ghrah.subject.workspace.providers.git import path_to_locator


def _seed_chain_db(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE runs (run_id TEXT PRIMARY KEY);
        CREATE TABLE agents (agent_name TEXT PRIMARY KEY, run_id TEXT NOT NULL);
        CREATE TABLE sessions (session_id TEXT PRIMARY KEY, agent_name TEXT NOT NULL);
        CREATE TABLE nodes (id TEXT PRIMARY KEY, agent_name TEXT NOT NULL);
        CREATE TABLE chain_meta (agent_name TEXT PRIMARY KEY);
        CREATE TABLE messages (agent_name TEXT PRIMARY KEY);
        INSERT INTO runs VALUES ('run-a'), ('run-b');
        INSERT INTO agents VALUES ('alice', 'run-a'), ('bob', 'run-b');
        INSERT INTO sessions VALUES ('session-a', 'alice'), ('session-b', 'bob');
        INSERT INTO nodes VALUES ('node-a', 'alice'), ('node-b', 'bob');
        INSERT INTO chain_meta VALUES ('alice'), ('bob');
        INSERT INTO messages VALUES ('alice'), ('bob');
        """
    )
    db.commit()
    db.close()


def _project(tmp_path: Path, project_id: str, agent_name: str):
    paths = ProjectPaths.from_locator(path_to_locator(str(tmp_path / project_id)))
    paths.initialize(project_id)
    return make_project_record(
        name=project_id, project_root_locator=paths.root_locator
    ).model_copy(
        update={
            "project_id": project_id,
            "agents": [AgentSpec(name=agent_name, cluster_id=f"cluster-{project_id}")],
        }
    )


async def test_action_chains_split_by_unique_agent_and_are_idempotent(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "ghrah.db"
    _seed_chain_db(legacy)
    alice = _project(tmp_path, "project-a", "alice")
    bob = _project(tmp_path, "project-b", "bob")

    report = await migrate_legacy_action_chains(legacy, [alice, bob])

    assert report.total_rows == 12
    assert report.ambiguous_agents == []
    assert Path(report.backup_path or "").is_file()
    for project, own_agent, other_agent in (
        (alice, "alice", "bob"),
        (bob, "bob", "alice"),
    ):
        target_path = ProjectPaths.from_locator(
            project.project_root_locator
        ).action_chain_db_path
        target = sqlite3.connect(target_path)
        try:
            names = {row[0] for row in target.execute("SELECT agent_name FROM agents")}
            assert own_agent in names
            assert other_agent not in names
        finally:
            target.close()

    rerun = await migrate_legacy_action_chains(legacy, [alice, bob])
    assert rerun.total_rows == 0


async def test_action_chain_dry_run_reports_ambiguous_ownership(tmp_path: Path) -> None:
    legacy = tmp_path / "ghrah.db"
    _seed_chain_db(legacy)
    first = _project(tmp_path, "project-a", "alice")
    second = _project(tmp_path, "project-b", "alice")

    report = await migrate_legacy_action_chains(
        legacy, [first, second], dry_run=True
    )

    assert report.ambiguous_agents == ["alice"]
    assert report.total_rows == 0
    assert report.backup_path is None
