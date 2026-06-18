from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SubjectEventBus
from ghrah.subject.manifest_store.store import ManifestStore
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import (
    CAPABILITY_REGISTRY,
    CORE_TRANSPORT,
    MANIFEST_STORE,
    WORKSPACE_SERVICE,
)
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units._commands import CORE_COMMANDS
from ghrah.subject.units.forward import ForwardUnit

AGENT_YAML = """\
manifest: agent
version: "1"
metadata:
  namespace: ghrah
  name: coder
  description: A coder agent
model:
  agent_config_name: default
system_prompt: You are a coder.
max_iterations: 20
abilities:
  - type: read_file
    permissions:
      require_hitl: true
      allowed_paths:
        - "{{workspace}}/src"
  - type: conversation
"""


class _FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[dict[str, Any], float | None]] = []

    @property
    def is_connected(self) -> bool:
        return True

    async def start(self, on_message: Any) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send(self, message: dict[str, Any]) -> None:
        self.sent.append((message, None))

    async def send_and_wait(
        self,
        message: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.sent.append((message, timeout))
        return {"success": True, "data": {"forwarded": message["type"]}}

    def resolve_command_result(
        self,
        request_id: str,
        payload: dict[str, Any],
    ) -> bool:
        return False


class _FakeWorkspaceService:
    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root
        self.resolved_agents: list[str] = []

    @property
    def root_path(self) -> str:
        return self._workspace_root

    async def create_workspace(self, agent_name: str) -> Any:
        return None

    def resolve_agent_path(self, agent_name: str) -> str | None:
        self.resolved_agents.append(agent_name)
        return str(Path(self._workspace_root) / agent_name)


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


def _context(
    config: SubjectConfig,
    unit: ForwardUnit,
    services: SubjectServices,
) -> SubjectContext:
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


def _manifest_store(tmp_path: Path) -> ManifestStore:
    store = ManifestStore(tmp_path / "manifests")
    store.ensure_dirs()
    store.put_agent("ghrah.coder", AGENT_YAML)
    return store


def test_forward_unit_meta_declares_hard_workspace_dependency() -> None:
    unit = ForwardUnit(SubjectConfig())

    assert unit.meta.name == "forward"
    assert unit.meta.routes.commands == frozenset()
    assert unit.meta.routes.long_running_commands == CORE_COMMANDS
    assert unit.meta.routes.commands.isdisjoint(unit.meta.routes.long_running_commands)
    key_names = {key.name for key in unit.meta.requires}
    assert key_names == {
        "manifest_store",
        "capability_registry",
        "core_transport",
        "workspace_service",
    }


async def test_spawn_agent_manifest_ref_materializes_permission_params(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    unit = ForwardUnit(config)
    transport = _FakeTransport()
    workspace = _FakeWorkspaceService(str(tmp_path / "workspace"))
    services = SubjectServices()
    services.set(CAPABILITY_REGISTRY, CapabilityRegistry())
    services.set(MANIFEST_STORE, _manifest_store(tmp_path))
    services.set(CORE_TRANSPORT, transport)
    services.set(WORKSPACE_SERVICE, workspace)

    await unit.init(_context(config, unit, services))
    result = await unit.handle_command(
        "spawn_agent",
        {"manifest_ref": "ghrah.coder", "config": {"name": "runtime-coder"}},
        CommandContext.observer("req-1", session_id="obs-1"),
    )

    assert result == {"success": True, "data": {"forwarded": "spawn_agent"}}
    assert workspace.resolved_agents == ["runtime-coder"]
    message, timeout = transport.sent[0]
    payload = message["payload"]
    workspace_root = str(Path(workspace.root_path) / "runtime-coder")

    assert timeout == 30.0
    assert message["request_id"] == "req-1"
    assert payload["manifest_ref"] is None
    assert payload["config"]["name"] == "runtime-coder"
    read_file = next(
        ability
        for ability in payload["abilities"]
        if ability["ability_type"] == "read_file"
    )
    conversation = next(
        ability
        for ability in payload["abilities"]
        if ability["ability_type"] == "conversation"
    )
    assert read_file["params"] == {
        "require_hitl": True,
        "workspace_root": workspace_root,
        "allowed_paths": [str(Path(workspace_root) / "src")],
    }
    assert conversation["params"] == {}


async def test_spawn_agent_manifest_ref_requires_workspace_service(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    unit = ForwardUnit(config)
    services = SubjectServices()
    services.set(CAPABILITY_REGISTRY, CapabilityRegistry())
    services.set(MANIFEST_STORE, _manifest_store(tmp_path))
    services.set(CORE_TRANSPORT, _FakeTransport())

    await unit.init(_context(config, unit, services))

    with pytest.raises(RuntimeError, match="workspace_service"):
        await unit.handle_command(
            "spawn_agent",
            {"manifest_ref": "ghrah.coder", "config": {"name": "runtime-coder"}},
            CommandContext.observer("req-1", session_id="obs-1"),
        )
