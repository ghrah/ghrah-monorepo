from __future__ import annotations

from pathlib import Path

from ghrah.context.node import ContextNode
from ghrah.context.persistence import serialize_node

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import LEDGER
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units.ledger import LedgerUnit


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_ledger_unit_registers_service_and_handles_history(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("ledger")
        assert isinstance(unit, LedgerUnit)
        assert engine.context.services.require(LEDGER) is unit.service

        missing_agent = await unit.handle_command(
            "get_chain_history",
            {},
            CommandContext.observer("req-1", session_id=None),
        )
        assert missing_agent == {"success": False, "error": "agent_name is required"}

        node = ContextNode.create_root(agent_name="agent-a", messages=[])
        await unit.handle_event(
            "action_chain_updated",
            {"agent_name": "agent-a", "node": serialize_node(node)},
        )
        result = await unit.handle_command(
            "get_chain_history",
            {"agent_name": "agent-a"},
            CommandContext.observer("req-2", session_id=None),
        )

        assert result["success"] is True
        assert result["data"]["agent_name"] == "agent-a"
        assert result["data"]["nodes"][0]["id"] == node.id
    finally:
        await engine.stop()
