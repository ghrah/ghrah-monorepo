# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Core transport protocol and in-process test transport."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, cast

from ghrah.protocol.types import generate_request_id  # type: ignore[import-untyped]

__all__ = [
    "CoreMessage",
    "CoreMessageHandler",
    "CoreTransport",
    "InProcessCoreTransport",
    "_PendingRequestTracker",
]

CoreMessage = dict[str, Any]
CoreMessageHandler = Callable[[CoreMessage], Awaitable[None]]


class CoreTransport(Protocol):
    """Transport service used by the Subject runtime to talk to Core."""

    @property
    def is_connected(self) -> bool:
        """Return whether the transport is connected."""

    async def start(self, on_message: CoreMessageHandler) -> None:
        """Start receiving Core messages."""

    async def stop(self) -> None:
        """Stop the transport and cancel pending requests."""

    async def send(self, message: CoreMessage) -> None:
        """Send a message to Core."""

    async def send_and_wait(
        self,
        message: CoreMessage,
        timeout: float | None = None,
    ) -> CoreMessage:
        """Send a request and wait for its command_result payload."""

    def resolve_command_result(self, request_id: str, payload: CoreMessage) -> bool:
        """Resolve a pending request from a command_result message."""


class _PendingRequestTracker:
    """Tracks request_id to Future mappings for request/response flows."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[CoreMessage]] = {}

    def register(self, request_id: str) -> asyncio.Future[CoreMessage]:
        """Register a pending request and return its future."""

        if request_id in self._pending:
            raise ValueError(f"Request '{request_id}' is already pending.")
        future: asyncio.Future[CoreMessage] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        return future

    def resolve(self, request_id: str, payload: Mapping[str, Any]) -> bool:
        """Resolve a pending request if it exists."""

        future = self._pending.pop(request_id, None)
        if future is None:
            return False
        if not future.done():
            future.set_result(dict(payload))
        return True

    def cancel(self, request_id: str) -> bool:
        """Cancel a single pending request."""

        future = self._pending.pop(request_id, None)
        if future is None:
            return False
        if not future.done():
            future.cancel()
        return True

    def cancel_all(self) -> int:
        """Cancel all pending requests and return the number cancelled."""

        pending = list(self._pending.values())
        self._pending.clear()
        for future in pending:
            if not future.done():
                future.cancel()
        return len(pending)

    @property
    def pending_count(self) -> int:
        """Return the number of pending requests."""

        return len(self._pending)


class InProcessCoreTransport:
    """CoreTransport fake used by runtime tests and local dispatcher integration."""

    def __init__(self) -> None:
        self._is_connected = False
        self._on_message: CoreMessageHandler | None = None
        self._pending = _PendingRequestTracker()
        self._sent: deque[CoreMessage] = deque()

    @property
    def is_connected(self) -> bool:
        """Return whether the fake transport has been started."""

        return self._is_connected

    @property
    def sent_messages(self) -> list[CoreMessage]:
        """Return messages sent through the fake transport."""

        return list(self._sent)

    @property
    def pending_count(self) -> int:
        """Return the number of pending request futures."""

        return self._pending.pending_count

    async def start(self, on_message: CoreMessageHandler) -> None:
        """Start the fake transport with an inbound message callback."""

        self._on_message = on_message
        self._is_connected = True

    async def stop(self) -> None:
        """Stop the fake transport and cancel pending requests."""

        self._is_connected = False
        self._on_message = None
        self._pending.cancel_all()

    async def send(self, message: CoreMessage) -> None:
        """Record a message sent to Core."""

        if not self._is_connected:
            raise RuntimeError("Core transport is not connected.")
        self._sent.append(dict(message))

    async def send_and_wait(
        self,
        message: CoreMessage,
        timeout: float | None = None,
    ) -> CoreMessage:
        """Record a message and wait for a matching command_result."""

        if not self._is_connected:
            raise RuntimeError("Core transport is not connected.")

        request = dict(message)
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            request_id = generate_request_id()
            request["request_id"] = request_id

        future = self._pending.register(request_id)
        await self.send(request)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending.cancel(request_id)
            raise
        except asyncio.CancelledError:
            self._pending.cancel(request_id)
            raise

    def resolve_command_result(self, request_id: str, payload: CoreMessage) -> bool:
        """Resolve a pending fake request."""

        return self._pending.resolve(request_id, payload)

    async def receive_injected(self, message: Mapping[str, Any]) -> None:
        """Inject a Core inbound message into the registered callback."""

        if not self._is_connected or self._on_message is None:
            raise RuntimeError("Core transport is not connected.")
        await self._on_message(cast(CoreMessage, dict(message)))
