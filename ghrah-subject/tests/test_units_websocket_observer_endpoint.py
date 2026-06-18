from __future__ import annotations

import asyncio
from typing import Any

from ghrah.protocol.types import EventType

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import (
    SUBJECT_CORE_EVENT_RECEIVED,
    SUBJECT_HITL_REQUEST_CREATED,
    SubjectEventBus,
)
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import (
    OBSERVER_ENDPOINT,
    OBSERVER_EVENT_BUS,
)
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.server.config import ObserverServerConfig
from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus
from ghrah.subject.server.router import ObserverRouter
from ghrah.subject.units.websocket_observer_endpoint import (
    WebSocketObserverEndpointUnit,
)


def _context(config: SubjectConfig, unit: WebSocketObserverEndpointUnit) -> SubjectContext:
    def create_task(coro: Any) -> asyncio.Task[Any]:
        return asyncio.create_task(coro)

    return SubjectContext(
        engine=SubjectEngine(config),
        config=config,
        event_bus=SubjectEventBus(),
        services=SubjectServices(),
        units={unit.meta.name: unit},
        create_task=create_task,
    )


async def test_observer_endpoint_composes_existing_server_components() -> None:
    config = SubjectConfig()
    unit = WebSocketObserverEndpointUnit(
        config,
        observer_config=ObserverServerConfig(ws_path="/observer"),
    )
    ctx = _context(config, unit)

    await unit.init(ctx)
    try:
        await unit.start()

        assert isinstance(unit.connection_manager, ConnectionManager)
        assert isinstance(unit.observer_event_bus, EventBus)
        assert isinstance(unit.router, ObserverRouter)
        assert ctx.services.require(OBSERVER_ENDPOINT) is unit
        assert ctx.services.require(OBSERVER_EVENT_BUS) is not unit.observer_event_bus
        assert any(getattr(route, "path", None) == "/observer" for route in unit.app.routes)
    finally:
        await unit.stop()


async def test_internal_core_and_hitl_events_forward_to_observer_event_bus() -> None:
    config = SubjectConfig()
    unit = WebSocketObserverEndpointUnit(config)
    ctx = _context(config, unit)

    await unit.init(ctx)
    try:
        await unit.start()

        await ctx.event_bus.emit(
            SUBJECT_CORE_EVENT_RECEIVED,
            {
                "event_type": "agent_spawned",
                "payload": {"name": "agent-a"},
            },
        )
        await ctx.event_bus.emit(
            SUBJECT_HITL_REQUEST_CREATED,
            {
                "promise_id": "promise-1",
                "agent_name": "agent-a",
                "ability_name": "write_file",
                "tool_args": {"file_path": "notes.md"},
            },
        )

        events = unit.observer_event_bus.event_store.replay_since(0)
        assert events[0]["type"] == "agent_spawned"
        assert events[0]["payload"] == {"name": "agent-a", "agent_name": "agent-a"}
        assert events[1]["type"] == EventType.HITL_REQUEST.value
        assert events[1]["payload"]["promise_id"] == "promise-1"
        assert events[1]["payload"]["agent_name"] == "agent-a"
    finally:
        await unit.stop()


async def test_observer_event_bus_service_adapter_publishes_wire_event() -> None:
    config = SubjectConfig()
    unit = WebSocketObserverEndpointUnit(config)
    ctx = _context(config, unit)

    await unit.init(ctx)
    try:
        await unit.start()
        adapter = ctx.services.require(OBSERVER_EVENT_BUS)

        count = await adapter.publish("agent_terminated", {"name": "agent-a"})

        assert count == 0
        events = unit.observer_event_bus.event_store.replay_since(0)
        assert events[-1]["type"] == "agent_terminated"
        assert events[-1]["payload"] == {"name": "agent-a", "agent_name": "agent-a"}
    finally:
        await unit.stop()
