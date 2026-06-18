from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ghrah.subject.transport.core import InProcessCoreTransport, _PendingRequestTracker


async def test_pending_request_tracker_register_resolve_and_cancel_all() -> None:
    tracker = _PendingRequestTracker()
    first = tracker.register("one")
    second = tracker.register("two")

    assert tracker.pending_count == 2
    assert tracker.resolve("one", {"success": True}) is True
    assert await first == {"success": True}

    cancelled = tracker.cancel_all()

    assert cancelled == 1
    assert second.cancelled()
    assert tracker.pending_count == 0


async def test_pending_request_tracker_rejects_duplicate_request_id() -> None:
    tracker = _PendingRequestTracker()
    tracker.register("same")

    with pytest.raises(ValueError, match="already pending"):
        tracker.register("same")


async def test_in_process_transport_send_receive_and_send_and_wait() -> None:
    transport = InProcessCoreTransport()
    received: list[dict[str, Any]] = []

    async def on_message(message: dict[str, Any]) -> None:
        received.append(message)

    await transport.start(on_message)
    await transport.send({"type": "event", "payload": {"ok": True}})
    await transport.receive_injected({"type": "inbound", "payload": {"id": 1}})

    request_task = asyncio.create_task(
        transport.send_and_wait(
            {"type": "request", "request_id": "req-1"},
            timeout=1.0,
        )
    )
    await asyncio.sleep(0)

    assert transport.sent_messages[0]["type"] == "event"
    assert transport.sent_messages[1]["request_id"] == "req-1"
    assert received == [{"type": "inbound", "payload": {"id": 1}}]

    assert transport.resolve_command_result("req-1", {"success": True}) is True
    assert await request_task == {"success": True}


async def test_in_process_transport_stop_cancels_pending_requests() -> None:
    transport = InProcessCoreTransport()

    async def on_message(message: dict[str, Any]) -> None:
        return None

    await transport.start(on_message)
    request_task = asyncio.create_task(
        transport.send_and_wait(
            {"type": "request", "request_id": "req-1"},
            timeout=10.0,
        )
    )
    await asyncio.sleep(0)

    assert transport.pending_count == 1

    await transport.stop()

    with pytest.raises(asyncio.CancelledError):
        await request_task
    assert transport.pending_count == 0


async def test_in_process_transport_requires_connection() -> None:
    transport = InProcessCoreTransport()

    with pytest.raises(RuntimeError, match="not connected"):
        await transport.send({"type": "event"})
