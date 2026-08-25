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
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_unit
from ghrah.subject.runtime.service_keys import LEDGER
from ghrah.subject.units.ledger import LedgerUnit


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_ledger_unit_reads_core_sqlite(tmp_path: Path) -> None:
    config = _config(tmp_path)

    # 模拟 Core 侧 agent 链落库（真相源；与 ledger 派生同一 core_db_path）
    writer = SqliteBackend(db_path=config.core_db_path)
    await writer.connect()
    root = ContextNode.create_root(agent_name="agent-a", messages=[])
    child = ContextNode(
        parent_id=root.id,
        agent_name="agent-a",
        iteration=1,
        ability_names=["tool_a"],
    )
    await writer.save_node(root)
    await writer.save_node(child)
    await writer.save_chain_meta(
        "agent-a",
        branches={"main": child.id},
        current_state={"phase": "run"},
        active_session_id="sess-1",
    )
    await writer.close()

    ledger = LedgerUnit(config)
    async with Context() as ctx:
        ledger_fiber = ctx.plugin(mount_unit(ledger))
        await wait_active(ledger_fiber)

        assert ctx.get(LEDGER.name) is ledger.service

        # agent_name 缺失 → 参数错误
        missing = await bridge_command(ctx, "get_chain_history", {})
        assert missing == {"success": False, "error": "agent_name is required"}

        # 读侧直连：命令返回 Core sqlite 中的节点
        result = await bridge_command(ctx, "get_chain_history", {"agent_name": "agent-a"})
        assert result["success"] is True
        data = result["data"]
        assert data["agent_name"] == "agent-a"
        assert data["active_session_id"] == "sess-1"
        assert [n["id"] for n in data["nodes"]] == [root.id, child.id]

        # 未知 agent → 空节点列表（成功）
        empty = await bridge_command(ctx, "get_chain_history", {"agent_name": "nobody"})
        assert empty["success"] is True
        assert empty["data"]["nodes"] == []
