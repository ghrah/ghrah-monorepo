from __future__ import annotations

import asyncio
from pathlib import Path

from ghrah.context.node import ContextNode
from ghrah.context.persistence import serialize_node
from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_unit
from ghrah.subject.runtime.service_keys import LEDGER
from ghrah.subject.units.ledger import LedgerUnit
from ghrah.subject.units.persistence import PersistenceUnit


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
    persistence = PersistenceUnit(config)
    ledger = LedgerUnit(config)

    async with Context() as ctx:
        ctx.plugin(mount_unit(persistence))
        ledger_fiber = ctx.plugin(mount_unit(ledger))
        await wait_active(ledger_fiber)

        assert ctx.get(LEDGER.name) is ledger.service

        missing_agent = await bridge_command(ctx, "get_chain_history", {})
        assert missing_agent == {"success": False, "error": "agent_name is required"}

        node = ContextNode.create_root(agent_name="agent-a", messages=[])
        ctx.emit(
            "event/action_chain_updated",
            {"agent_name": "agent-a", "node": serialize_node(node)},
        )
        # emit 将 async listener 调度为后台任务，轮询至节点落账
        for _ in range(200):
            result = await bridge_command(ctx, "get_chain_history", {"agent_name": "agent-a"})
            if result.get("success") and result.get("data", {}).get("nodes"):
                break
            await asyncio.sleep(0.01)

        assert result["success"] is True
        assert result["data"]["agent_name"] == "agent-a"
        assert result["data"]["nodes"][0]["id"] == node.id
