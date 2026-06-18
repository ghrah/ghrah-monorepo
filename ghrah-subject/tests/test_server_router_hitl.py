from __future__ import annotations

from typing import Any

from ghrah.protocol.types import CommandType, Message

from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus
from ghrah.subject.server.router import ObserverRouter


async def test_observer_router_hitl_response_uses_handler_result() -> None:
    async def hitl_response_handler(payload: dict[str, Any]) -> dict[str, Any]:
        assert payload == {"promise_id": "missing"}
        return {
            "success": False,
            "error": "HITL promise not found or expired: missing",
        }

    connection_manager = ConnectionManager()
    event_bus = EventBus(connection_manager)
    router = ObserverRouter(
        connection_manager,
        event_bus,
        hitl_response_handler=hitl_response_handler,
    )

    result = await router.handle_command(
        Message(
            type=CommandType.HITL_RESPONSE.value,
            payload={"promise_id": "missing"},
            request_id="req-1",
        ),
        session_id="session-1",
    )

    assert result is not None
    assert result.payload.success is False
    assert result.payload.error == "HITL promise not found or expired: missing"
