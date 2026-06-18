from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from ghrah.subject.config import CoreTransportConfig
from ghrah.subject.units.websocket_core_transport import (
    WebSocketCoreTransport,
    build_core_websocket_url,
)

_END = object()


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.incoming: asyncio.Queue[Any] = asyncio.Queue()

    def __aiter__(self) -> _FakeWebSocket:
        return self

    async def __anext__(self) -> Any:
        item = await self.incoming.get()
        if item is _END:
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            raise item
        return item

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    async def finish(self) -> None:
        await self.incoming.put(_END)


def test_build_core_websocket_url_preserves_existing_query() -> None:
    assert build_core_websocket_url("ws://core/ws?x=1", "cid") == (
        "ws://core/ws?x=1&client_type=subject&client_id=cid"
    )


async def test_send_receive_and_send_and_wait_with_mock_websocket() -> None:
    connections: list[tuple[str, dict[str, Any], _FakeWebSocket]] = []

    async def connect(url: str, **kwargs: Any) -> _FakeWebSocket:
        ws = _FakeWebSocket()
        connections.append((url, kwargs, ws))
        return ws

    received: list[dict[str, Any]] = []
    received_event = asyncio.Event()

    async def on_message(message: dict[str, Any]) -> None:
        received.append(message)
        received_event.set()

    transport = WebSocketCoreTransport(
        CoreTransportConfig(url="ws://core/ws?x=1"),
        client_id="cid",
        connect_factory=connect,
    )
    await transport.start(on_message)
    try:
        ws = connections[0][2]
        assert transport.is_connected is True
        assert connections[0][0] == (
            "ws://core/ws?x=1&client_type=subject&client_id=cid"
        )
        assert connections[0][1]["ping_interval"] == 30.0

        await transport.send({"type": "ping"})
        assert json.loads(ws.sent[-1]) == {"type": "ping"}

        request_task = asyncio.create_task(
            transport.send_and_wait(
                {"type": "spawn_agent", "request_id": "req-1"},
                timeout=1.0,
            )
        )
        await asyncio.sleep(0)
        assert transport.pending_count == 1
        assert json.loads(ws.sent[-1])["request_id"] == "req-1"

        assert transport.resolve_command_result("req-1", {"success": True}) is True
        assert await request_task == {"success": True}

        await ws.incoming.put('{"type": "agent_spawned", "payload": {"name": "a"}}')
        await asyncio.wait_for(received_event.wait(), timeout=1.0)
        assert received == [{"type": "agent_spawned", "payload": {"name": "a"}}]
    finally:
        await transport.stop()


async def test_disconnect_cancels_pending_request() -> None:
    connections: list[_FakeWebSocket] = []

    async def connect(url: str, **kwargs: Any) -> _FakeWebSocket:
        del url, kwargs
        ws = _FakeWebSocket()
        connections.append(ws)
        return ws

    async def on_message(message: dict[str, Any]) -> None:
        del message

    transport = WebSocketCoreTransport(
        CoreTransportConfig(max_reconnect_attempts=0),
        connect_factory=connect,
    )
    await transport.start(on_message)
    try:
        request_task = asyncio.create_task(
            transport.send_and_wait(
                {"type": "send_message", "request_id": "req-2"},
                timeout=10.0,
            )
        )
        await asyncio.sleep(0)
        assert transport.pending_count == 1

        await connections[0].finish()

        with pytest.raises(asyncio.CancelledError):
            await request_task
        assert transport.pending_count == 0
    finally:
        await transport.stop()


async def test_disconnect_reconnects_with_mock_websocket() -> None:
    connections: list[_FakeWebSocket] = []
    reconnected = asyncio.Event()

    async def connect(url: str, **kwargs: Any) -> _FakeWebSocket:
        del url, kwargs
        ws = _FakeWebSocket()
        connections.append(ws)
        if len(connections) == 2:
            reconnected.set()
        return ws

    async def sleep(delay: float) -> None:
        del delay

    async def on_message(message: dict[str, Any]) -> None:
        del message

    transport = WebSocketCoreTransport(
        CoreTransportConfig(reconnect_interval=0.01, max_reconnect_attempts=1),
        connect_factory=connect,
        sleep=sleep,
    )
    await transport.start(on_message)
    try:
        await connections[0].finish()
        await asyncio.wait_for(reconnected.wait(), timeout=1.0)
        assert len(connections) == 2
        assert transport.is_connected is True
    finally:
        await transport.stop()
