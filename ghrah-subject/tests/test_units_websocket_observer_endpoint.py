from __future__ import annotations

import asyncio
from typing import Any

from ghrah.protocol.types import EventType
from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import mount_unit
from ghrah.subject.runtime.service_keys import (
    OBSERVER_ENDPOINT,
    OBSERVER_EVENT_BUS,
)
from ghrah.subject.server.config import ObserverServerConfig
from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus
from ghrah.subject.server.router import ObserverRouter
from ghrah.subject.units.websocket_observer_endpoint import (
    WebSocketObserverEndpointUnit,
    _EngineDispatchAdapter,
)


async def test_observer_endpoint_composes_existing_server_components() -> None:
    config = SubjectConfig()
    unit = WebSocketObserverEndpointUnit(
        config,
        observer_config=ObserverServerConfig(ws_path="/observer"),
    )

    async with Context() as ctx:
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber)

        assert isinstance(unit.connection_manager, ConnectionManager)
        assert isinstance(unit.observer_event_bus, EventBus)
        assert isinstance(unit.router, ObserverRouter)
        assert ctx.get(OBSERVER_ENDPOINT.name) is unit
        assert ctx.get(OBSERVER_EVENT_BUS.name) is not unit.observer_event_bus
        assert any(getattr(route, "path", None) == "/observer" for route in unit.app.routes)


async def test_unified_events_forward_to_observer_event_bus() -> None:
    config = SubjectConfig()
    unit = WebSocketObserverEndpointUnit(config)

    async with Context() as ctx:
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber)

        # 事件统一：core 域（core:{type}）与 subject 域（event/{type}）双前缀直发
        ctx.emit("core:agent_spawned", {"name": "agent-a"})
        ctx.emit("event/task_created", {"task_id": "t-1"})
        ctx.emit(
            f"core:{EventType.HITL_REQUEST.value}",
            {
                "promise_id": "promise-1",
                "agent_name": "agent-a",
                "ability_name": "write_file",
                "tool_args": {"file_path": "notes.md"},
            },
        )

        # emit 将 async forward 回调调度为后台任务，轮询至三条事件落库
        events: list[dict[str, Any]] = []
        for _ in range(200):
            events = unit.observer_event_bus.event_store.replay_since(0)
            if len(events) >= 3:
                break
            await asyncio.sleep(0.01)

        assert events[0]["type"] == "agent_spawned"
        assert events[0]["payload"] == {"name": "agent-a", "agent_name": "agent-a"}
        assert events[1]["type"] == "task_created"
        assert events[1]["payload"]["task_id"] == "t-1"
        assert events[2]["type"] == EventType.HITL_REQUEST.value
        assert events[2]["payload"]["promise_id"] == "promise-1"
        assert events[2]["payload"]["agent_name"] == "agent-a"


async def test_observer_event_bus_service_adapter_publishes_wire_event() -> None:
    config = SubjectConfig()
    unit = WebSocketObserverEndpointUnit(config)

    async with Context() as ctx:
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber)

        adapter = ctx.get(OBSERVER_EVENT_BUS.name)

        count = await adapter.publish("agent_terminated", {"name": "agent-a"})

        assert count == 0
        events = unit.observer_event_bus.event_store.replay_since(0)
        assert events[-1]["type"] == "agent_terminated"
        assert events[-1]["payload"] == {"name": "agent-a", "agent_name": "agent-a"}


async def test_observer_scoped_agent_command_routes_to_uuid_cluster() -> None:
    class ProjectManagerStub:
        async def handle_command(
            self, command: str, payload: dict[str, Any]
        ) -> dict[str, Any]:
            return {
                "success": True,
                "data": {
                    "project": {
                        "project_id": "p1",
                        "project_root_locator": "file:///tmp/p1",
                        "agents": [
                            {"agent_id": "a" * 32, "name": "planner", "cluster_id": "c1"},
                            {"agent_id": "b" * 32, "name": "planner", "cluster_id": "c2"},
                        ],
                    }
                },
            }

    class HandleStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        async def dispatch(
            self, command: str, payload: dict[str, Any]
        ) -> dict[str, Any]:
            self.calls.append((command, payload))
            return {"success": True, "data": {"routed": True}, "error": None}

    class RegistryStub:
        def __init__(self) -> None:
            self.handles = {"c1": HandleStub(), "c2": HandleStub()}

        async def ensure_cluster(
            self, cluster_id: str, *, project_root_locator: str = ""
        ) -> HandleStub:
            return self.handles[cluster_id]

    class ContextStub:
        def __init__(self) -> None:
            self.registry = RegistryStub()

        def get(self, name: str) -> Any:
            if name == "project_manager":
                return ProjectManagerStub()
            if name == "core_cluster_registry":
                return self.registry
            raise KeyError(name)

    ctx = ContextStub()
    adapter = _EngineDispatchAdapter(ctx)
    result = await adapter.dispatch_observer_command(
        "send_message",
        {
            "project_id": "p1",
            "agent_id": "b" * 32,
            "target": "planner",
            "content": "resume",
        },
    )

    assert result["success"] is True
    assert ctx.registry.handles["c1"].calls == []
    assert ctx.registry.handles["c2"].calls == [
        ("send_message", {"target": "planner", "content": "resume"})
    ]
