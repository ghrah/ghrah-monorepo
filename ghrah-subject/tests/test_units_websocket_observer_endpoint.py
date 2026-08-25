from __future__ import annotations

import asyncio
from typing import Any

from ghrah.protocol.types import EventType
from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import (
    SUBJECT_CORE_EVENT_RECEIVED,
    SUBJECT_HITL_REQUEST_CREATED,
)
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


async def test_internal_core_and_hitl_events_forward_to_observer_event_bus() -> None:
    config = SubjectConfig()
    unit = WebSocketObserverEndpointUnit(config)

    async with Context() as ctx:
        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber)

        ctx.emit(
            f"event/{SUBJECT_CORE_EVENT_RECEIVED}",
            {
                "event_type": "agent_spawned",
                "payload": {"name": "agent-a"},
            },
        )
        ctx.emit(
            f"event/{SUBJECT_HITL_REQUEST_CREATED}",
            {
                "promise_id": "promise-1",
                "agent_name": "agent-a",
                "ability_name": "write_file",
                "tool_args": {"file_path": "notes.md"},
            },
        )

        # emit 将 async forward 回调调度为后台任务，轮询至两条事件落库
        events: list[dict[str, Any]] = []
        for _ in range(200):
            events = unit.observer_event_bus.event_store.replay_since(0)
            if len(events) >= 2:
                break
            await asyncio.sleep(0.01)

        assert events[0]["type"] == "agent_spawned"
        assert events[0]["payload"] == {"name": "agent-a", "agent_name": "agent-a"}
        assert events[1]["type"] == EventType.HITL_REQUEST.value
        assert events[1]["payload"]["promise_id"] == "promise-1"
        assert events[1]["payload"]["agent_name"] == "agent-a"


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
