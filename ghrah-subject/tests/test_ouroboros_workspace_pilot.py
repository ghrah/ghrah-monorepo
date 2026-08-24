# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ouroboros 深度替换试点测试（上位计划 1787015082781 阶段 1）。

验证 workspace unit 经 ``unit_to_plugin`` 包装后能在 Ouroboros ``Context``
上：挂载 → 服务可见 → 命令路由 → 卸载回退（服务+路由消失）→ 重挂恢复。
sandbox unit 作为依赖被同一包装器挂载，验证 unit 间服务依赖经 Ouroboros
``provide``/``inject`` 解析成立。

旧基建（SubjectEngine/SubjectContext/SubjectServices）未动，原
``test_units_workspace.py`` / ``test_units_sandbox.py`` 走旧基建仍须绿
（见任务 4 对照验证）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ouroboros import Context, FiberState  # type: ignore[import-untyped]

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, unit_to_plugin
from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.units.sandbox import SandboxUnit
from ghrah.subject.units.workspace import WorkspaceUnit


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_workspace_on_ouroboros_mount_provide_route_dispose_remount(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    async with Context() as ctx:
        sandbox_fiber = ctx.plugin(unit_to_plugin(SandboxUnit(config)), config)
        await sandbox_fiber.await_()
        assert sandbox_fiber.state is FiberState.ACTIVE

        ws_fiber = ctx.plugin(unit_to_plugin(WorkspaceUnit(config)), config)
        await ws_fiber.await_()
        assert ws_fiber.state is FiberState.ACTIVE

        sandbox = ctx.get("sandbox_executor")
        assert isinstance(sandbox, SandboxExecutor)
        assert ctx.get("workspace_service") is not None
        assert ctx.get("workspace_manager") is not None

        missing = await bridge_command(
            ctx, "workspace_status", {"agent_name": "missing"}
        )
        assert missing == {
            "success": False,
            "error": "Workspace not found for agent 'missing'",
        }

        created = await bridge_command(
            ctx, "create_workspace", {"agent_name": "agent-a"}
        )
        assert created["success"] is True
        assert created["data"]["agent_name"] == "agent-a"
        assert "path" in created["data"]

        await ws_fiber.dispose()
        await asyncio.sleep(0.05)

        assert ctx.get("workspace_service", strict=False) is None
        assert ctx.get("workspace_manager", strict=False) is None

        gone = await bridge_command(
            ctx, "workspace_status", {"agent_name": "missing"}
        )
        assert gone == {"success": False, "error": "Unknown command: workspace_status"}

        ws_fiber2 = ctx.plugin(unit_to_plugin(WorkspaceUnit(config)), config)
        await ws_fiber2.await_()
        assert ws_fiber2.state is FiberState.ACTIVE

        assert ctx.get("workspace_service") is not None
        recovered = await bridge_command(
            ctx, "workspace_status", {"agent_name": "missing"}
        )
        assert recovered == {
            "success": False,
            "error": "Workspace not found for agent 'missing'",
        }

        await ws_fiber2.dispose()


async def test_bridge_command_unknown_returns_unknown_command(tmp_path: Path) -> None:
    async with Context() as ctx:
        result = await bridge_command(ctx, "nonexistent_command", {})
        assert result == {
            "success": False,
            "error": "Unknown command: nonexistent_command",
        }


async def test_sandbox_dispose_drops_service(tmp_path: Path) -> None:
    config = _config(tmp_path)

    async with Context() as ctx:
        sandbox_fiber = ctx.plugin(unit_to_plugin(SandboxUnit(config)), config)
        await sandbox_fiber.await_()
        assert ctx.get("sandbox_executor") is not None

        await sandbox_fiber.dispose()
        await asyncio.sleep(0.05)
        assert ctx.get("sandbox_executor", strict=False) is None
