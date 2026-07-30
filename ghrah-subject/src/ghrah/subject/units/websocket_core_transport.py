# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WebSocket Core transport built-in Subject unit."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast
from urllib.parse import urlencode, urlparse, urlunparse

import websockets

from ghrah.protocol.types import generate_request_id  # type: ignore[import-untyped]
from ghrah.subject.config import CoreTransportConfig, SubjectConfig
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import CORE_TRANSPORT
from ghrah.subject.transport.core import CoreMessage, CoreMessageHandler, _PendingRequestTracker
from ghrah.subject.unit.base import SubjectUnit, UnitMeta

__all__ = [
    "WebSocketCoreTransport",
    "WebSocketCoreTransportUnit",
    "build_core_websocket_url",
]

logger = logging.getLogger(__name__)

ConnectFactory = Callable[..., Awaitable[Any]]
SleepCallable = Callable[[float], Awaitable[Any]]


class WebSocketCoreTransport:
    """Default WebSocket implementation of the CoreTransport protocol."""

    def __init__(
        self,
        config: CoreTransportConfig,
        *,
        client_id: str | None = None,
        connect_factory: ConnectFactory | None = None,
        sleep: SleepCallable = asyncio.sleep,
    ) -> None:
        self._config = config
        self._client_id = client_id or uuid.uuid4().hex[:16]
        self._connect: ConnectFactory = connect_factory or websockets.connect
        self._sleep = sleep
        self._pending = _PendingRequestTracker()
        self._ws: Any = None
        self._on_message: CoreMessageHandler | None = None
        self._running = False
        self._receive_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        """Return whether a WebSocket is currently connected."""

        return self._running and self._ws is not None

    @property
    def pending_count(self) -> int:
        """Return the number of pending request futures."""

        return self._pending.pending_count

    @property
    def client_id(self) -> str:
        """Return the stable client id used in the Core URL."""

        return self._client_id

    async def start(self, on_message: CoreMessageHandler) -> None:
        """Connect once and start the background receive/reconnect loop."""

        if self._running:
            self._on_message = on_message
            return

        self._on_message = on_message
        self._running = True
        try:
            await self._connect_once()
        except Exception:
            self._running = False
            self._pending.cancel_all()
            raise
        self._receive_task = asyncio.create_task(
            self._receive_loop(),
            name="subject-core-websocket-transport",
        )

    async def stop(self) -> None:
        """Stop the transport, close the socket, and cancel pending requests."""

        self._running = False
        self._pending.cancel_all()

        task = self._receive_task
        self._receive_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        await self._close_current_websocket()
        self._on_message = None

    async def send(self, message: CoreMessage) -> None:
        """Send a JSON message to Core."""

        if self._ws is None:
            raise RuntimeError("Core transport is not connected.")
        await self._ws.send(json.dumps(message, ensure_ascii=False))

    async def send_and_wait(
        self,
        message: CoreMessage,
        timeout: float | None = None,
    ) -> CoreMessage:
        """Send a request and wait for a matching command_result payload."""

        if self._ws is None:
            raise RuntimeError("Core transport is not connected.")

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

    async def _connect_once(self) -> None:
        url = build_core_websocket_url(self._config.url, self._client_id)
        self._ws = await self._connect(
            url,
            ping_interval=self._config.ping_interval,
            ping_timeout=10,
        )
        logger.info("WebSocketCoreTransport connected to Core at %s", url)
        await self._send_init_cluster()

    async def _send_init_cluster(self) -> None:
        """连接/重连成功后自动发 init_cluster（D-strict 必要适配，幂等重绑定）。

        fire-and-forget：同一 WS 上消息有序，init 先于后续命令到达 Core；
        同 client_id 重连时 Core 侧 ConnectionManager 已 evict 旧 session（解绑），
        故重发 init 可幂等重绑定。发送失败仅 log warning 不阻断连接。
        """

        message: CoreMessage = {
            "type": "init_cluster",
            "payload": {"cluster_id": self._config.cluster_id},
            "request_id": generate_request_id(),
        }
        try:
            await self.send(message)
        except Exception:
            logger.warning(
                "WebSocketCoreTransport failed to send init_cluster(cluster_id=%s); "
                "connection remains usable but agent commands may be rejected until retry.",
                self._config.cluster_id,
            )
            return
        logger.info(
            "WebSocketCoreTransport sent init_cluster(cluster_id=%s).",
            self._config.cluster_id,
        )

    async def _receive_loop(self) -> None:
        while self._running:
            try:
                await self._receive_current_connection()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("WebSocketCoreTransport receive loop failed.")

            await self._handle_disconnect()
            if not self._running:
                break
            if not await self._reconnect():
                break

    async def _receive_current_connection(self) -> None:
        ws = self._ws
        if ws is None:
            return
        async for raw in ws:
            if not self._running:
                break
            on_message = self._on_message
            if on_message is None:
                continue
            await on_message(_decode_core_message(raw))

    async def _handle_disconnect(self) -> None:
        cancelled = self._pending.cancel_all()
        if cancelled:
            logger.warning(
                "WebSocketCoreTransport cancelled %d pending request(s) after disconnect.",
                cancelled,
            )
        await self._close_current_websocket()

    async def _reconnect(self) -> bool:
        attempts = 0
        while self._running:
            max_attempts = self._config.max_reconnect_attempts
            if max_attempts is not None and attempts >= max_attempts:
                logger.error(
                    "WebSocketCoreTransport exhausted %d reconnect attempt(s).",
                    max_attempts,
                )
                self._running = False
                return False

            attempts += 1
            await self._sleep(self._config.reconnect_interval)
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "WebSocketCoreTransport reconnect attempt %d failed: %s",
                    attempts,
                    exc,
                )
                continue
            return True
        return False

    async def _close_current_websocket(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is None:
            return
        close = getattr(ws, "close", None)
        if callable(close):
            await close()


class WebSocketCoreTransportUnit(SubjectUnit):
    """Unit wrapper that provides the CORE_TRANSPORT service."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ctx: SubjectContext | None = None
        self._transport: WebSocketCoreTransport | None = None
        self._meta = UnitMeta(
            name="websocket_core_transport",
            provides=frozenset({CORE_TRANSPORT}),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> WebSocketCoreTransport:
        if self._transport is None:
            raise RuntimeError("WebSocketCoreTransportUnit has not been initialized.")
        return self._transport

    async def init(self, ctx: SubjectContext) -> None:
        self._ctx = ctx
        self._transport = WebSocketCoreTransport(ctx.config.core)
        ctx.services.set(CORE_TRANSPORT, self._transport)

    async def start(self) -> None:
        if self._ctx is None:
            raise RuntimeError("WebSocketCoreTransportUnit has not been initialized.")
        await self.service.start(self._ctx.dispatcher.dispatch_core_message)

    async def stop(self) -> None:
        if self._transport is not None:
            await self._transport.stop()


def build_core_websocket_url(base_url: str, client_id: str) -> str:
    """Add Subject client query params to a Core WebSocket URL."""

    parts = urlparse(base_url)
    params = {"client_type": "subject", "client_id": client_id}
    extra_query = urlencode(params)
    new_query = f"{parts.query}&{extra_query}" if parts.query else extra_query
    return urlunparse(parts._replace(query=new_query))


def _decode_core_message(raw: Any) -> CoreMessage:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, bytes | bytearray):
        raw = raw.decode()
    if isinstance(raw, str):
        decoded = json.loads(raw)
        if isinstance(decoded, Mapping):
            return dict(decoded)
        raise ValueError(f"Core message JSON must decode to an object, got {type(decoded)!r}.")
    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        return cast(CoreMessage, model_dump())
    raise TypeError(f"Unsupported Core WebSocket message type: {type(raw)!r}")
