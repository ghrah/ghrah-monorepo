"""ClusterHandle spawn materializer 集成测试（D3）。

验证 ``ClusterTransportUnit.init`` 经 ``MANIFEST_STORE`` + ``WORKSPACE_SERVICE``
构造的 spawn 物化器，注入 manager → handle，使 ``ClusterHandle.spawn_agent`` 对带
``manifest_ref`` 的 payload 自动展开 manifest 为具体 abilities。

逻辑迁自 ``test_units_forward.py``，改用真实 handle 路径（经 ClusterTransportManager →
ClusterHandle），而非 ForwardUnit 直接 forward。物化器用 ``ClusterTransportUnit``
模块内 ``_build_spawn_materializer`` 真实构造（与 unit.init 同一函数）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from ghrah.protocol.types import AgentConfigPayload, SpawnAgentPayload

from ghrah.subject.cluster_transport import ClusterHandle, ClusterTransportManager
from ghrah.subject.config import CoreTransportConfig, SubjectConfig
from ghrah.subject.event_bus import SubjectEventBus
from ghrah.subject.manifest_store.store import ManifestStore
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import (
    CAPABILITY_REGISTRY,
    CLUSTER_TRANSPORT_MANAGER,
    MANIFEST_STORE,
    WORKSPACE_SERVICE,
)
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.transport.core import CoreMessage, InProcessCoreTransport
from ghrah.subject.units.cluster_transport import (
    ClusterTransportUnit,
    _build_spawn_materializer,
)

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

    def resolve_agent_default_path(self, agent_name: str) -> str | None:
        return self.resolve_agent_path(agent_name)

    def get_workspace_record(self, workspace_id: str) -> Any | None:
        return None


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


def _manifest_store(tmp_path: Path) -> ManifestStore:
    store = ManifestStore(tmp_path / "manifests")
    store.ensure_dirs()
    store.put_agent("ghrah.coder", AGENT_YAML)
    return store


def _fake_factory(
    captures: dict[str, InProcessCoreTransport],
) -> Any:
    def make(config: CoreTransportConfig) -> InProcessCoreTransport:
        t = InProcessCoreTransport()
        captures[config.cluster_id] = t
        return t

    return make


def _cr(success: bool, data: Any = None, error: str | None = None) -> CoreMessage:
    return {
        "type": "command_result",
        "payload": {"success": success, "data": data, "error": error},
    }


def _ctx(
    config: SubjectConfig,
    unit: ClusterTransportUnit,
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


@pytest.fixture
async def manager(
    tmp_path: Path,
) -> AsyncIterator[
    tuple[ClusterTransportManager, dict[str, InProcessCoreTransport], _FakeWorkspaceService]
]:
    """构造带真实物化器的 manager（InProcessCoreTransport 工厂，无真实 WS）。

    物化器经 ``_build_spawn_materializer`` 真实构造（与 unit.init 同函数）。
    """
    store = _manifest_store(tmp_path)
    workspace = _FakeWorkspaceService(str(tmp_path / "workspace"))
    materializer = _build_spawn_materializer(store, workspace)
    captures: dict[str, InProcessCoreTransport] = {}
    m = ClusterTransportManager(
        CoreTransportConfig(),
        on_message=lambda msg, *, source: asyncio.sleep(0),
        transport_factory=_fake_factory(captures),
        spawn_materializer=materializer,
    )
    try:
        yield m, captures, workspace
    finally:
        await m.stop()


class TestClusterHandleSpawnMaterialize:
    def test_unit_meta_declares_manifest_and_workspace_requires(self) -> None:
        unit = ClusterTransportUnit(SubjectConfig())
        assert unit.meta.name == "cluster_transport"
        assert unit.meta.routes.commands == frozenset()
        key_names = {key.name for key in unit.meta.requires}
        assert key_names == {"manifest_store", "workspace_service"}

    async def test_unit_init_constructs_manager_with_materializer(
        self, tmp_path: Path
    ) -> None:
        """unit.init 经 services 构造物化器并注入 manager（真实接线验证）。"""
        config = _config(tmp_path)
        unit = ClusterTransportUnit(config)
        services = SubjectServices()
        services.set(CAPABILITY_REGISTRY, CapabilityRegistry())
        services.set(MANIFEST_STORE, _manifest_store(tmp_path))
        services.set(WORKSPACE_SERVICE, _FakeWorkspaceService(str(tmp_path / "workspace")))
        ctx = _ctx(config, unit, services)

        await unit.init(ctx)

        manager = ctx.services.require(CLUSTER_TRANSPORT_MANAGER)
        assert manager is unit.service
        assert manager._spawn_materializer is not None  # type: ignore[attr-defined]
        await manager.stop()

    async def test_manifest_ref_materializes_abilities(
        self,
        manager: tuple[
            ClusterTransportManager, dict[str, InProcessCoreTransport], _FakeWorkspaceService
        ],
    ) -> None:
        m, captures, workspace = manager
        handle = await m.ensure_cluster("default")
        transport = captures["default"]

        async def respond() -> None:
            await asyncio.sleep(0.01)
            sent = transport.sent_messages[-1]
            transport.resolve_command_result(
                sent["request_id"], _cr(True, {"name": "runtime-coder"})
            )

        asyncio.create_task(respond())
        result = await handle.spawn_agent(
            SpawnAgentPayload(
                config=AgentConfigPayload(name="runtime-coder"),
                manifest_ref="ghrah.coder",
            )
        )
        assert result["success"] is True
        assert workspace.resolved_agents == ["runtime-coder"]

        sent = transport.sent_messages[-1]
        assert sent["type"] == "spawn_agent"
        payload = sent["payload"]
        assert payload["manifest_ref"] is None
        assert payload["config"]["name"] == "runtime-coder"
        abilities = payload["abilities"]
        assert abilities is not None
        read_file = next(a for a in abilities if a["ability_type"] == "read_file")
        conversation = next(a for a in abilities if a["ability_type"] == "conversation")
        workspace_root = str(Path(workspace.root_path) / "runtime-coder")
        assert read_file["params"] == {
            "require_hitl": True,
            "workspace_root": workspace_root,
            "allowed_paths": [str(Path(workspace_root) / "src")],
        }
        assert conversation["params"] == {}

    async def test_no_manifest_ref_passes_through(
        self,
        manager: tuple[
            ClusterTransportManager, dict[str, InProcessCoreTransport], _FakeWorkspaceService
        ],
    ) -> None:
        m, captures, _workspace = manager
        handle = await m.ensure_cluster("default")
        transport = captures["default"]

        async def respond() -> None:
            await asyncio.sleep(0.01)
            sent = transport.sent_messages[-1]
            transport.resolve_command_result(sent["request_id"], _cr(True))

        asyncio.create_task(respond())
        result = await handle.spawn_agent(
            SpawnAgentPayload(
                config=AgentConfigPayload(name="plain"),
                abilities=None,
                manifest_ref=None,
            )
        )
        assert result["success"] is True
        sent = transport.sent_messages[-1]
        payload = sent["payload"]
        assert payload["manifest_ref"] is None
        assert payload["abilities"] is None
        assert payload["config"]["name"] == "plain"

    async def test_handle_is_cluster_handle(
        self,
        manager: tuple[
            ClusterTransportManager, dict[str, InProcessCoreTransport], _FakeWorkspaceService
        ],
    ) -> None:
        m, _captures, _workspace = manager
        handle = await m.ensure_cluster("default")
        assert isinstance(handle, ClusterHandle)
