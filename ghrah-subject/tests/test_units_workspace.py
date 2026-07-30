from __future__ import annotations

from pathlib import Path

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import WORKSPACE_SERVICE
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units.workspace import WorkspaceUnit


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_workspace_unit_registers_typed_service_and_missing_workspace_result(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("workspace")
        assert isinstance(unit, WorkspaceUnit)

        service = engine.context.services.require(WORKSPACE_SERVICE)
        existing_path = Path(service.root_path) / "agent-existing"
        existing_path.mkdir()

        assert service is unit.service
        assert service.resolve_agent_path("agent-existing") == str(existing_path)
        assert service.resolve_agent_path("missing") is None

        result = await unit.handle_command(
            "workspace_status",
            {"agent_name": "missing"},
            CommandContext.observer("req-1", session_id=None),
        )
        assert result == {
            "success": False,
            "error": "Workspace not found for agent 'missing'",
        }
    finally:
        await engine.stop()


async def test_workspace_register_get_list_commands(tmp_path: Path) -> None:
    """workspace_register/get/list 3 新命令（W6）。"""
    from ghrah.subject.workspace import path_to_locator

    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("workspace")
        assert isinstance(unit, WorkspaceUnit)

        # 先建一个 agent 默认 workspace，使其出现在 list 中
        created = await unit.handle_command(
            "create_workspace",
            {"agent_name": "agent-a"},
            CommandContext.observer("req-1", session_id=None),
        )
        assert created["success"] is True

        # register：把一个已存在的目录登记为 plain workspace
        import os

        data_dir = os.path.join(config.sandbox.workspace_root, "data-dir")
        os.makedirs(data_dir)
        reg = await unit.handle_command(
            "workspace_register",
            {"locator": path_to_locator(data_dir), "name": "data", "provider_type": "plain"},
            CommandContext.observer("req-2", session_id=None),
        )
        assert reg["success"] is True
        wid = reg["data"]["workspace_id"]
        assert reg["data"]["provider_type"] == "plain"

        # get：按 workspace_id 取记录
        got = await unit.handle_command(
            "workspace_get",
            {"workspace_id": wid},
            CommandContext.observer("req-3", session_id=None),
        )
        assert got["success"] is True
        assert got["data"]["workspace_id"] == wid
        assert got["data"]["name"] == "data"

        # get：未知 workspace_id 失败
        miss = await unit.handle_command(
            "workspace_get",
            {"workspace_id": "nope"},
            CommandContext.observer("req-4", session_id=None),
        )
        assert miss["success"] is False

        # list：无过滤含 agent-a 与 data
        lst = await unit.handle_command(
            "workspace_list",
            {},
            CommandContext.observer("req-5", session_id=None),
        )
        assert lst["success"] is True
        ids = {w["workspace_id"] for w in lst["data"]["workspaces"]}
        assert wid in ids

        # list：按 plain 过滤只剩 data
        lst_plain = await unit.handle_command(
            "workspace_list",
            {"provider_type": "plain"},
            CommandContext.observer("req-6", session_id=None),
        )
        plain_ids = {w["workspace_id"] for w in lst_plain["data"]["workspaces"]}
        assert plain_ids == {wid}
    finally:
        await engine.stop()
