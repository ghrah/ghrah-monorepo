from __future__ import annotations

from pathlib import Path

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import PERSISTENCE
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units.persistence import PersistenceUnit


async def test_persistence_unit_lifecycle_and_service_registration(tmp_path: Path) -> None:
    config = SubjectConfig(db_path=str(tmp_path / "subject.db"))
    unit = PersistenceUnit(config)
    engine = SubjectEngine(config)
    engine.register_unit(unit)

    await engine.start()
    try:
        assert engine.context.services.require(PERSISTENCE) is unit.service
        result = await unit.handle_command(
            "persist_list_agents",
            {},
            CommandContext.observer("req-1", session_id=None),
        )
        assert result["success"] is True
    finally:
        await engine.stop()
