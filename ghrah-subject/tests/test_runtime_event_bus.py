from __future__ import annotations

import logging
from typing import Any

from ghrah.subject.event_bus import SubjectEventBus


async def test_emit_broadcasts_to_subscribers() -> None:
    bus = SubjectEventBus()
    received: list[tuple[str, Any]] = []

    async def handler(event_type: str, payload: Any) -> None:
        received.append((event_type, payload))

    bus.subscribe("subject.test", handler)

    await bus.emit("subject.test", {"ok": True})

    assert received == [("subject.test", {"ok": True})]


async def test_handler_failure_is_isolated(caplog: Any) -> None:
    bus = SubjectEventBus()
    received: list[tuple[str, Any]] = []

    async def bad_handler(event_type: str, payload: Any) -> None:
        raise RuntimeError(f"boom:{event_type}:{payload['id']}")

    async def good_handler(event_type: str, payload: Any) -> None:
        received.append((event_type, payload))

    bus.subscribe("subject.test", bad_handler)
    bus.subscribe("subject.test", good_handler)

    with caplog.at_level(logging.WARNING):
        await bus.emit("subject.test", {"id": 1})

    assert received == [("subject.test", {"id": 1})]
    assert "Subject event handler failed for subject.test" in caplog.text


def test_event_bus_has_no_query_apis() -> None:
    bus = SubjectEventBus()

    assert not hasattr(bus, "query")
    assert not hasattr(bus, "subscribe_sync")
