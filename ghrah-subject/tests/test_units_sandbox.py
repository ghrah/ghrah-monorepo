from __future__ import annotations

from pathlib import Path

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import SANDBOX_EXECUTOR
from ghrah.subject.units.sandbox import SandboxUnit


async def test_sandbox_unit_lifecycle_and_service_registration(tmp_path: Path) -> None:
    config = SubjectConfig(workspace_root=str(tmp_path / "workspace"))
    unit = SandboxUnit(config)
    engine = SubjectEngine(config)
    engine.register_unit(unit)

    await engine.start()
    try:
        service = engine.context.services.require(SANDBOX_EXECUTOR)
        assert service is unit.service
        assert service.workspace_root == str(tmp_path / "workspace")
        assert service.config.default_timeout == config.sandbox.default_timeout
    finally:
        await engine.stop()
