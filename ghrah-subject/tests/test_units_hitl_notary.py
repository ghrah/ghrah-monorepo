from __future__ import annotations

from pathlib import Path

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import HITL_NOTARY
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units.hitl_notary import HITLNotaryUnit


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_hitl_notary_unit_response_success_and_unknown_false(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("hitl_notary")
        assert isinstance(unit, HITLNotaryUnit)
        assert engine.context.services.require(HITL_NOTARY) is unit.service

        unknown = await unit.handle_command(
            "hitl_response",
            {"promise_id": "missing", "approved": True},
            CommandContext.observer("req-1", session_id=None),
        )
        assert unknown == {
            "success": False,
            "error": "HITL promise not found or expired: missing",
        }

        promise = unit.service.create_promise(
            "agent-a",
            "write_file",
            {"file_path": "a.txt"},
        )
        resolved = await unit.handle_command(
            "hitl_response",
            {
                "promise_id": promise.promise_id,
                "approved": True,
                "reason": "ok",
            },
            CommandContext.observer("req-2", session_id=None),
        )

        assert resolved == {
            "success": True,
            "data": {"processed": True, "promise_id": promise.promise_id},
        }
        assert promise.future.result().approved is True
        assert promise.future.result().reason == "ok"
    finally:
        await engine.stop()
