# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Core connection layer: connection + reconnect + init_cluster handshake.

D4 分层：``CoreConnection`` 仅管连接/重连/init_cluster 握手；request-response
跟踪留给上层 :class:`ghrah.subject.transport.core.CoreTransport`。本模块提供
``CoreConnection`` Protocol 与默认的 WebSocket 实现 ``WebSocketCoreConnection``
（从原 ``units/websocket_core_transport.py`` 平移 WS 连接逻辑），并暴露
``build_core_websocket_url`` / ``_decode_core_message`` 工具。

入站消息经 ``RawCoreMessageHandler`` 回调交上层 transport；connection 不感知
``source``，source 关联由 transport 层（持自身引用注入偏函数）完成（D1）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, cast
from urllib.parse import urlencode, urlparse, urlunparse

import websockets

from ghrah.protocol.types import generate_request_id  # type: ignore[import-untyped]
from ghrah.subject.config import CoreTransportConfig
from ghrah.subject.transport.core import CoreMessage, RawCoreMessageHandler

__all__ = [
    "CoreConnection",
    "WebSocketCoreConnection",
    "build_core_websocket_url",
]

logger = logging.getLogger(__name__)

ConnectFactory = Callable[..., Awaitable[Any]]
SleepCallable = Callable[[float], Awaitable[Any]]


class CoreConnection(Protocol):
    """连接层契约：建连 + 重连 + init_cluster 握手 + 原始消息回调。"""

    @property
    def cluster_id(self) -> str:
        """该 connection 绑定的 Core cluster id。"""

    @property
    def is_connected(self) -> bool:
        """连接是否处于已建立状态。"""

    async def start(self, on_message: RawCoreMessageHandler) -> None:
        """建 WS + 起 receive/reconnect 循环。

        on_message 签名见 D1：``on_message(msg)``（connection 不感知 source；
        source 由上层 transport 持有自身引用注入）。
        """

    async def stop(self) -> None:
        """停止连接、关闭 socket、中断重连循环。"""

    async def send(self, message: CoreMessage) -> None:
        """发送一条 JSON 消息到 Core（要求已连接）。"""


class WebSocketCoreConnection:
    """WebSocket 实现 of :class:`CoreConnection`。

    平移原 ``WebSocketCoreTransport`` 的 WS 连接 + 重连 + _send_init_cluster
    逻辑；不含 _PendingRequestTracker（留给 transport 层）。

    断线回调 ``on_disconnect``：构造期注入，断线时触发（供上层 transport
    取消 pending request，符合 D4）。
    """

    def __init__(
        self,
        config: CoreTransportConfig,
        *,
        client_id: str | None = None,
        connect_factory: ConnectFactory | None = None,
        sleep: SleepCallable = asyncio.sleep,
        on_disconnect: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._client_id = client_id or uuid.uuid4().hex[:16]
        self._connect: ConnectFactory = connect_factory or websockets.connect
        self._sleep = sleep
        self._on_disconnect = on_disconnect
        self._ws: Any = None
        self._on_message: RawCoreMessageHandler | None = None
        self._running = False
        self._receive_task: asyncio.Task[None] | None = None

    @property
    def cluster_id(self) -> str:
        return self._config.cluster_id

    @property
    def is_connected(self) -> bool:
        return self._running and self._ws is not None

    @property
    def client_id(self) -> str:
        """返回稳定 client id（Core URL 用）。"""

        return self._client_id

    async def start(self, on_message: RawCoreMessageHandler) -> None:
        """建连一次并启动后台 receive/reconnect 循环。"""

        if self._running:
            self._on_message = on_message
            return

        self._on_message = on_message
        self._running = True
        try:
            await self._connect_once()
        except Exception:
            self._running = False
            await self._notify_disconnect()
            raise
        self._receive_task = asyncio.create_task(
            self._receive_loop(),
            name="subject-core-websocket-connection",
        )

    async def stop(self) -> None:
        """停止连接、关闭 socket、取消 receive 循环。"""

        self._running = False

        task = self._receive_task
        self._receive_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        await self._close_current_websocket()
        self._on_message = None

    async def send(self, message: CoreMessage) -> None:
        """发送 JSON 消息到 Core（要求已连接）。"""

        if self._ws is None:
            raise RuntimeError("Core connection is not connected.")
        await self._ws.send(json.dumps(message, ensure_ascii=False))

    async def _connect_once(self) -> None:
        url = build_core_websocket_url(self._config.url, self._client_id)
        self._ws = await self._connect(
            url,
            ping_interval=self._config.ping_interval,
            ping_timeout=10,
        )
        logger.info("WebSocketCoreConnection connected to Core at %s", url)
        await self._send_init_cluster()

    async def _send_init_cluster(self) -> None:
        """连接/重连成功后自动发 init_cluster（幂等重绑定）。

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
                "WebSocketCoreConnection failed to send init_cluster(cluster_id=%s); "
                "connection remains usable but agent commands may be rejected until retry.",
                self._config.cluster_id,
            )
            return
        logger.info(
            "WebSocketCoreConnection sent init_cluster(cluster_id=%s).",
            self._config.cluster_id,
        )

    async def _receive_loop(self) -> None:
        while self._running:
            try:
                await self._receive_current_connection()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("WebSocketCoreConnection receive loop failed.")

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
        await self._close_current_websocket()
        await self._notify_disconnect()

    async def _notify_disconnect(self) -> None:
        """断线回调（供上层 transport 取消 pending request）。"""

        on_disconnect = self._on_disconnect
        if on_disconnect is None:
            return
        try:
            await on_disconnect()
        except Exception:  # noqa: BLE001
            logger.exception("on_disconnect callback failed.")

    async def _reconnect(self) -> bool:
        attempts = 0
        while self._running:
            max_attempts = self._config.max_reconnect_attempts
            if max_attempts is not None and attempts >= max_attempts:
                logger.error(
                    "WebSocketCoreConnection exhausted %d reconnect attempt(s).",
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
                    "WebSocketCoreConnection reconnect attempt %d failed: %s",
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
