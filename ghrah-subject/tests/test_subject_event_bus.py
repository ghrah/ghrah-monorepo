from __future__ import annotations

from typing import Any

from ghrah.protocol.types import EventType, HealthStatusPayload, Message

from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


async def test_publish_without_agent_name_is_not_filtered_by_agent_subscription() -> None:
    manager = ConnectionManager()
    websocket = _FakeWebSocket()
    await manager.connect("observer-1", websocket)
    manager.subscribe("observer-1", agent_names=["agent-a"])
    bus = EventBus(manager)

    count = await bus.publish(
        Message(
            type=EventType.HEALTH_STATUS.value,
            payload=HealthStatusPayload(status={"ok": True}),
        )
    )

    assert count == 1
    assert websocket.sent[0]["type"] == EventType.HEALTH_STATUS.value
