# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Core transport layer: CoreTransport Protocol + request/response tracking.

D4 分层：本模块的 ``CoreTransport`` 持 connection + ``_PendingRequestTracker``，
管 ``send`` / ``send_and_wait`` / ``resolve_command_result``；连接本身（建连/
重连/init_cluster）由 :mod:`ghrah.subject.transport.conn` 的 ``CoreConnection``
负责。``WebSocketCoreTransport`` 持 ``WebSocketCoreConnection`` + tracker，
``start(on_message)`` 把 ``on_message(msg, self)`` 包装为 ``RawCoreMessageHandler``
后交给 connection。

D1 入站关联：``CoreMessageHandler`` 带 ``source: CoreTransport``；
``RawCoreMessageHandler`` 为 connection 层用别名（不带 source）。
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast

from ghrah.protocol.types import generate_request_id  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from ghrah.subject.config import CoreTransportConfig
    from ghrah.subject.transport.conn import ConnectFactory, SleepCallable

__all__ = [
    "CoreMessage",
    "CoreMessageHandler",
    "CoreTransport",
    "InProcessCoreTransport",
    "RawCoreMessageHandler",
    "WebSocketCoreTransport",
    "_PendingRequestTracker",
]

CoreMessage = dict[str, Any]


class CoreTransport(Protocol):
    """Transport service used by the Subject runtime to talk to Core."""

    @property
    def is_connected(self) -> bool:
        """Return whether the transport is connected."""

    async def start(self, on_message: CoreMessageHandler) -> None:
        """Start receiving Core messages.

        on_message 签名见 D1：``on_message(msg, source)``，source 为接收到
        该消息的 transport 自身（用于 resolve/pong/reply 回路由）。
        """

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


class CoreMessageHandler(Protocol):
    """入站 Core 消息回调（D1：带 ``source``）。

    ``source`` 为接收到该消息的 transport 自身，用于 resolve/pong/reply 回路由。
    transport 层经关键字 ``source=`` 调用；dispatcher 侧 ``dispatch_core_message``
    声明 ``*, source`` 对齐。
    """

    def __call__(self, message: CoreMessage, *, source: CoreTransport) -> Awaitable[None]:
        """处理一条入站 Core 消息。"""


RawCoreMessageHandler = Callable[[CoreMessage], Awaitable[None]]


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


class WebSocketCoreTransport:
    """WebSocket implementation of the CoreTransport protocol.

    持 :class:`WebSocketCoreConnection`（连接 + 重连 + init_cluster）与
    :class:`_PendingRequestTracker`（request-response 跟踪）。

    ``start(on_message)``：把上层 ``on_message(msg, source)`` 包装为
    ``RawCoreMessageHandler`` 后交给 connection；断线回调注入
    ``self._pending.cancel_all``（D4：pending 取消留 transport 层）。
    """

    def __init__(
        self,
        config: CoreTransportConfig,
        *,
        client_id: str | None = None,
        connect_factory: ConnectFactory | None = None,
        sleep: SleepCallable = asyncio.sleep,
    ) -> None:
        # 延迟导入避免循环（conn 不反向 import core）。
        from ghrah.subject.transport.conn import WebSocketCoreConnection

        self._pending = _PendingRequestTracker()
        self._on_message: CoreMessageHandler | None = None

        async def _on_disconnect() -> None:
            self._pending.cancel_all()

        self._connection = WebSocketCoreConnection(
            config,
            client_id=client_id,
            connect_factory=connect_factory,
            sleep=sleep,
            on_disconnect=_on_disconnect,
        )

    @property
    def is_connected(self) -> bool:
        """Return whether the underlying connection is currently connected."""

        return self._connection.is_connected

    @property
    def pending_count(self) -> int:
        """Return the number of pending request futures."""

        return self._pending.pending_count

    @property
    def client_id(self) -> str:
        """Return the stable client id used in the Core URL."""

        return self._connection.client_id

    async def start(self, on_message: CoreMessageHandler) -> None:
        """Connect once and start the background receive/reconnect loop.

        把上层 ``on_message(msg, source)`` 包装为 ``RawCoreMessageHandler``
        （注入 ``source=self``）后交给 connection。
        """

        self._on_message = on_message
        await self._connection.start(self._raw_on_message)

    async def stop(self) -> None:
        """Stop the transport, close the connection, cancel pending requests."""

        self._pending.cancel_all()
        await self._connection.stop()
        self._on_message = None

    async def send(self, message: CoreMessage) -> None:
        """Send a JSON message to Core via the connection."""

        await self._connection.send(message)

    async def send_and_wait(
        self,
        message: CoreMessage,
        timeout: float | None = None,
    ) -> CoreMessage:
        """Send a request and wait for a matching command_result payload."""

        request = dict(message)
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            request_id = generate_request_id()
            request["request_id"] = request_id

        future = self._pending.register(request_id)
        try:
            await self.send(request)
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending.cancel(request_id)
            raise
        except asyncio.CancelledError:
            self._pending.cancel(request_id)
            raise
        except Exception:
            self._pending.cancel(request_id)
            raise

    def resolve_command_result(self, request_id: str, payload: CoreMessage) -> bool:
        """Resolve a pending request future."""

        return self._pending.resolve(request_id, payload)

    async def _raw_on_message(self, message: CoreMessage) -> None:
        """Connection 层回调：注入 ``source=self`` 后转上层 handler。"""

        on_message = self._on_message
        if on_message is None:
            return
        await on_message(message, source=self)


class InProcessCoreTransport:
    """CoreTransport fake used by runtime tests and local dispatcher integration.

    D1 同步：``start`` / ``receive_injected`` 经 ``self._on_message(msg, self)``
    注入 source（自身），使其仍满足 ``CoreTransport`` Protocol。
    """

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
        await self._on_message(cast(CoreMessage, dict(message)), source=self)
