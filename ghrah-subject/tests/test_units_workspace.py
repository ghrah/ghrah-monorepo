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
