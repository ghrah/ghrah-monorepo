from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import (
    SUBJECT_CORE_EVENT_RECEIVED,
    SUBJECT_MANIFEST_PERMISSIONS_CHANGED,
    SubjectEventBus,
)
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import CAPABILITY_REGISTRY, MANIFEST_PERMISSION_INDEX
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units._helpers import (
    manifest_command_to_event,
    manifest_result_to_event_payload,
)
from ghrah.subject.units.manifest_store import ManifestStoreUnit

CUSTOM_ABILITY_YAML = """\
manifest: ability
version: "1"
metadata:
  namespace: custom
  name: needs_hitl
  description: Needs approval
  permissions:
    require_hitl: true
tool:
  name: needs_hitl
  description: Needs approval
  parameters: {}
implementation:
  type: builtin
  handler: custom_needs_hitl
"""


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


def _context(config: SubjectConfig, unit: ManifestStoreUnit) -> SubjectContext:
    services = SubjectServices()
    services.set(CAPABILITY_REGISTRY, CapabilityRegistry())

    def create_task(coro: Any) -> asyncio.Task[Any]:
        return asyncio.create_task(coro)

    return SubjectContext(
        engine=SubjectEngine(config),
        config=config,
        event_bus=SubjectEventBus(),
        services=services,
        units={unit.meta.name: unit},
        create_task=create_task,
    )


def test_manifest_command_to_event_maps_only_crud_commands() -> None:
    assert manifest_command_to_event("manifest_put_ability", {}) == (
        "manifest_ability_created"
    )
    assert manifest_command_to_event("manifest_put_ability", {"overwrite": True}) == (
        "manifest_ability_updated"
    )
    assert manifest_command_to_event("manifest_delete_ability", {}) == (
        "manifest_ability_deleted"
    )
    assert manifest_command_to_event("manifest_put_agent", {}) == "manifest_agent_created"
    assert manifest_command_to_event("manifest_delete_agent", {}) == "manifest_agent_deleted"
    assert manifest_command_to_event("manifest_list_abilities", {}) is None
    assert manifest_command_to_event("manifest_validate", {}) is None


def test_manifest_result_to_event_payload_keeps_wire_shape() -> None:
    result = {
        "success": True,
        "data": {
            "full_name": "custom.needs_hitl",
            "manifest": {"manifest": "ability"},
            "source": "manifest: ability",
        },
    }

    assert manifest_result_to_event_payload(result) == {
        "full_name": "custom.needs_hitl",
        "namespace": "custom",
        "manifest": {"manifest": "ability"},
        "source": "manifest: ability",
    }


async def test_manifest_store_unit_refreshes_permission_index_after_crud(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    unit = ManifestStoreUnit(config)
    ctx = _context(config, unit)
    emitted: list[tuple[str, Any]] = []

    async def collect(event_type: str, payload: Any) -> None:
        emitted.append((event_type, payload))

    ctx.event_bus.subscribe(SUBJECT_MANIFEST_PERMISSIONS_CHANGED, collect)
    ctx.event_bus.subscribe(SUBJECT_CORE_EVENT_RECEIVED, collect)

    await unit.init(ctx)
    permission_index = ctx.services.require(MANIFEST_PERMISSION_INDEX)

    assert "custom_needs_hitl" not in permission_index.get_permissions()

    put_result = await unit.handle_command(
        "manifest_put_ability",
        {"full_name": "custom.needs_hitl", "content": CUSTOM_ABILITY_YAML},
        CommandContext.observer("req-1", session_id=None),
    )

    permissions = permission_index.get_permissions()
    assert put_result["success"] is True
    assert permissions["custom_needs_hitl"].require_hitl is True
    assert (
        SUBJECT_MANIFEST_PERMISSIONS_CHANGED,
        {},
    ) in emitted
    assert (
        SUBJECT_CORE_EVENT_RECEIVED,
        {
            "event_type": "manifest_ability_created",
            "payload": {
                "full_name": "custom.needs_hitl",
                "namespace": "custom",
                "manifest": put_result["data"]["manifest"],
                "source": put_result["data"]["source"],
            },
        },
    ) in emitted

    delete_result = await unit.handle_command(
        "manifest_delete_ability",
        {"full_name": "custom.needs_hitl"},
        CommandContext.observer("req-2", session_id=None),
    )

    assert delete_result["success"] is True
    assert "custom_needs_hitl" not in permission_index.get_permissions()
