from __future__ import annotations

from pathlib import Path

from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_unit
from ghrah.subject.runtime.service_keys import PERSISTENCE
from ghrah.subject.units.persistence import PersistenceUnit


async def test_persistence_unit_lifecycle_and_service_registration(tmp_path: Path) -> None:
    config = SubjectConfig(db_path=str(tmp_path / "subject.db"))
    unit = PersistenceUnit(config)

    async with Context() as ctx:
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber)

        assert ctx.get(PERSISTENCE.name) is unit.service
        result = await bridge_command(ctx, "persist_list_agents", {})
        assert result["success"] is True

        await fiber.dispose()
        assert ctx.get(PERSISTENCE.name, strict=False) is None
