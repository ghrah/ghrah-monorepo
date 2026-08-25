from __future__ import annotations

from pathlib import Path

from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_unit
from ghrah.subject.runtime.service_keys import HITL_NOTARY
from ghrah.subject.units.hitl_notary import HITLNotaryUnit
from ghrah.subject.units.hitl_policy import HITLPolicyUnit
from ghrah.subject.units.manifest_store import ManifestStoreUnit


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
    unit = HITLNotaryUnit(config)

    async with Context() as ctx:
        # 依赖链：manifest_store → hitl_policy → hitl_notary
        ctx.plugin(mount_unit(ManifestStoreUnit(config)))
        ctx.plugin(mount_unit(HITLPolicyUnit(config)))
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber)

        assert ctx.get(HITL_NOTARY.name) is unit.service

        unknown = await bridge_command(
            ctx,
            "hitl_response",
            {"promise_id": "missing", "approved": True},
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
        resolved = await bridge_command(
            ctx,
            "hitl_response",
            {
                "promise_id": promise.promise_id,
                "approved": True,
                "reason": "ok",
            },
        )

        assert resolved == {
            "success": True,
            "data": {"processed": True, "promise_id": promise.promise_id},
        }
        assert promise.future.result().approved is True
        assert promise.future.result().reason == "ok"
