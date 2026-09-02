# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""LedgerUnit 测试（读侧直连 Core sqlite 形态）。

聚合裁决 D-C：无事件驱动写侧（旧 ``event/action_chain_updated`` 面已死）；
本文件用真实 SqliteBackend 预写 agent 链（模拟 Core 侧落库），断言
``get_chain_history`` 命令经 ctx.serial 路由到读侧投影。
"""

from __future__ import annotations

from pathlib import Path

from ghrah.context.node import ContextNode
from ghrah.context.persistence.sqlite_backend import (  # type: ignore[import-untyped]
    SqliteBackend,
)
from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.config import SubjectConfig
from ghrah.subject.project.paths import ProjectPaths
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_unit
from ghrah.subject.runtime.service_keys import LEDGER, PROJECT_MANAGER
from ghrah.subject.units.ledger import LedgerUnit


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_ledger_unit_reads_core_sqlite(tmp_path: Path) -> None:
    config = _config(tmp_path)
    project_id = "project-a"
    agent_id = "agent-a-id"
    paths = ProjectPaths.from_locator((tmp_path / "project-a-root").as_uri())
    paths.action_chain_db_path.parent.mkdir(parents=True, exist_ok=True)

    # 模拟 Core 侧 agent 链落入目标 Project Root。
    writer = SqliteBackend(db_path=paths.action_chain_db_path)
    await writer.connect()
    root = ContextNode.create_root(agent_name=agent_id, messages=[])
    child = ContextNode(
        parent_id=root.id,
        agent_name=agent_id,
        iteration=1,
        ability_names=["tool_a"],
    )
    await writer.save_node(root)
    await writer.save_node(child)
    await writer.save_chain_meta(
        agent_id,
        branches={"main": child.id},
        current_state={"phase": "run"},
        active_session_id="sess-1",
    )
    await writer.close()

    class FakeProjectManager:
        async def handle_command(self, command: str, payload: dict[str, object]):
            assert command == "project_get"
            return {
                "success": True,
                "data": {
                    "project": {
                        "project_id": project_id,
                        "project_root_locator": paths.root.as_uri(),
                        "agents": [
                            {
                                "name": "agent-a",
                                "agent_id": agent_id,
                                "cluster_id": "default",
                            }
                        ],
                    }
                },
            }

    ledger = LedgerUnit(config)
    async with Context() as ctx:
        ctx.provide(PROJECT_MANAGER.name, FakeProjectManager())
        ledger_fiber = ctx.plugin(mount_unit(ledger))
        await wait_active(ledger_fiber)

        # D6：实例级 ledger 不再发布为 LEDGER 服务（无全局库读后门）。
        try:
            provided = ctx.get(LEDGER.name)
        except Exception:  # noqa: BLE001 — 未注册服务的两种表现都算未发布
            provided = None
        assert provided is None

        # 任何缺失的作用域字段都被严格拒绝。
        missing = await bridge_command(ctx, "get_chain_history", {})
        assert missing["success"] is False

        result = await bridge_command(
            ctx,
            "get_chain_history",
            {
                "project_id": project_id,
                "agent_id": agent_id,
                "agent_name": "agent-a",
            },
        )
        assert result["success"] is True
        data = result["data"]
        assert data["agent_name"] == "agent-a"
        assert data["active_session_id"] == "sess-1"
        assert [n["id"] for n in data["nodes"]] == [root.id, child.id]

        wrong = await bridge_command(
            ctx,
            "get_chain_history",
            {
                "project_id": project_id,
                "agent_id": "other-agent",
                "agent_name": "agent-a",
            },
        )
        assert wrong["success"] is False
        assert wrong["error"] == "agent_project_mismatch"


async def test_ledger_resolves_project_agent_name_to_checkpoint_agent_id(
    tmp_path: Path,
) -> None:
    """恢复后 SQLite 以 UUID 分区，旧 UI 的 name 查询仍应返回完整链。"""
    config = _config(tmp_path)
    project_id = "project-1"
    agent_id = "agent-uuid-1"
    paths = ProjectPaths.from_locator((tmp_path / "project-root").as_uri())
    paths.action_chain_db_path.parent.mkdir(parents=True, exist_ok=True)

    writer = SqliteBackend(db_path=paths.action_chain_db_path)
    await writer.connect()
    root = ContextNode.create_root(agent_name=agent_id, messages=[])
    child = ContextNode(
        parent_id=root.id,
        agent_name=agent_id,
        iteration=1,
        ability_names=["conversation"],
    )
    await writer.save_node(root)
    await writer.save_node(child)
    await writer.save_chain_meta(
        agent_id,
        branches={"main": child.id},
        current_state={},
        active_session_id="session-1",
    )
    await writer.close()

    class FakeProjectManager:
        async def handle_command(self, command: str, payload: dict[str, object]):
            assert command == "project_get"
            return {
                "success": True,
                "data": {
                    "project": {
                        "project_id": project_id,
                        "project_root_locator": paths.root.as_uri(),
                        "agents": [
                            {
                                "name": "shuoxi",
                                "agent_id": agent_id,
                                "cluster_id": "default",
                            }
                        ],
                    }
                },
            }

    ledger = LedgerUnit(config)
    async with Context() as ctx:
        ctx.provide(PROJECT_MANAGER.name, FakeProjectManager())
        fiber = ctx.plugin(mount_unit(ledger))
        await wait_active(fiber)

        result = await bridge_command(
            ctx,
            "get_chain_history",
            {
                "agent_name": "shuoxi",
                "agent_id": agent_id,
                "project_id": project_id,
            },
        )

        assert result["success"] is True
        assert result["data"]["agent_name"] == "shuoxi"
        assert result["data"]["agent_id"] == agent_id
        assert [node["id"] for node in result["data"]["nodes"]] == [root.id, child.id]


async def test_same_agent_name_chain_history_isolated_by_project_root(
    tmp_path: Path,
) -> None:
    """同名 Agent 必须按 Project Root 与稳定 agent_id 双重隔离。"""
    config = _config(tmp_path)
    projects = {
        "project-a": {
            "agent_id": "agent-a-id",
            "paths": ProjectPaths.from_locator((tmp_path / "project-a-root").as_uri()),
        },
        "project-b": {
            "agent_id": "agent-b-id",
            "paths": ProjectPaths.from_locator((tmp_path / "project-b-root").as_uri()),
        },
    }
    expected_node_ids: dict[str, list[str]] = {}
    for project_id, project in projects.items():
        agent_id = project["agent_id"]
        paths = project["paths"]
        assert isinstance(agent_id, str)
        assert isinstance(paths, ProjectPaths)
        paths.action_chain_db_path.parent.mkdir(parents=True, exist_ok=True)
        writer = SqliteBackend(db_path=paths.action_chain_db_path)
        await writer.connect()
        root = ContextNode.create_root(agent_name=agent_id, messages=[])
        child = ContextNode(
            parent_id=root.id,
            agent_name=agent_id,
            iteration=1,
            ability_names=[project_id],
        )
        await writer.save_node(root)
        await writer.save_node(child)
        await writer.save_chain_meta(
            agent_id,
            branches={"main": child.id},
            current_state={"project_id": project_id},
            active_session_id=f"session-{project_id}",
        )
        await writer.close()
        expected_node_ids[project_id] = [root.id, child.id]

    class FakeProjectManager:
        async def handle_command(self, command: str, payload: dict[str, object]):
            assert command == "project_get"
            project_id = str(payload["project_id"])
            project = projects[project_id]
            paths = project["paths"]
            assert isinstance(paths, ProjectPaths)
            return {
                "success": True,
                "data": {
                    "project": {
                        "project_id": project_id,
                        "project_root_locator": paths.root.as_uri(),
                        "agents": [
                            {
                                "name": "shared-name",
                                "agent_id": project["agent_id"],
                                "cluster_id": "default",
                            }
                        ],
                    }
                },
            }

    ledger = LedgerUnit(config)
    async with Context() as ctx:
        ctx.provide(PROJECT_MANAGER.name, FakeProjectManager())
        fiber = ctx.plugin(mount_unit(ledger))
        await wait_active(fiber)

        for project_id, project in projects.items():
            result = await bridge_command(
                ctx,
                "get_chain_history",
                {
                    "project_id": project_id,
                    "agent_id": project["agent_id"],
                    "agent_name": "shared-name",
                },
            )
            assert result["success"] is True
            assert result["data"]["project_id"] == project_id
            assert [node["id"] for node in result["data"]["nodes"]] == (
                expected_node_ids[project_id]
            )

        cross_project = await bridge_command(
            ctx,
            "get_chain_history",
            {
                "project_id": "project-a",
                "agent_id": projects["project-b"]["agent_id"],
                "agent_name": "shared-name",
            },
        )
        assert cross_project["success"] is False
        assert cross_project["error"] == "agent_project_mismatch"
