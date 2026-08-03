# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ClusterTransportManager：per-cluster WS transport 句柄管理。

每 cluster 一条独立 :class:`WebSocketCoreTransport`
框架支持复数。

``on_message`` 回调由 unit 注入（dispatcher.dispatch_core_message），各 transport
共用。D1：各 transport 的 ``start`` 自动带 ``source``（transport 自身）注入，
回执 resolve / pong / reply 经接收到该消息的 transport 的 tracker 完成。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from ghrah.subject.cluster_transport.handle import ClusterHandle, SpawnMaterializer
from ghrah.subject.config import CoreTransportConfig
from ghrah.subject.transport.core import (
    CoreMessageHandler,
    CoreTransport,
    WebSocketCoreTransport,
)

logger = logging.getLogger(__name__)

__all__ = ["ClusterTransportManager"]

TransportFactory = Callable[[CoreTransportConfig], CoreTransport]


class ClusterTransportManager:
    """per-cluster WS transport 句柄管理器。

    Attributes:
        _core_config: 模板 CoreTransportConfig（每 cluster 复制并替换 cluster_id）。
        _handles: cluster_id → ClusterHandle。
        _on_message: 各 transport 共用的 Core 消息回调（unit 注入）。
        _transport_factory: 构造 transport 的工厂（默认 WebSocketCoreTransport，
            测试可注入 fake）。
    """

    def __init__(
        self,
        core_config: CoreTransportConfig,
        *,
        on_message: CoreMessageHandler | None = None,
        transport_factory: TransportFactory | None = None,
        spawn_materializer: SpawnMaterializer | None = None,
    ) -> None:
        self._core_config = core_config
        self._handles: dict[str, ClusterHandle] = {}
        self._on_message = on_message
        self._transport_factory = transport_factory or _default_transport_factory
        self._spawn_materializer = spawn_materializer
        self._lock = asyncio.Lock()

    async def ensure_cluster(self, cluster_id: str) -> ClusterHandle:
        """幂等建/取某 cluster 的 handle。

        已有则直接返回；无则新建 transport（复制 core_config 替换 cluster_id）→
        start(on_message) → 包装 ClusterHandle。transport 连接建立时自动发
        init_cluster（幂等重绑定）。

        Raises:
            RuntimeError: on_message 未注入。
        """
        async with self._lock:
            existing = self._handles.get(cluster_id)
            if existing is not None:
                return existing
            if self._on_message is None:
                raise RuntimeError(
                    "ClusterTransportManager.on_message not set; call set_on_message "
                    "before ensure_cluster."
                )
            cfg = _with_cluster_id(self._core_config, cluster_id)
            transport = self._transport_factory(cfg)
            on_message = self._on_message
            # D1：transport.start 的 on_message 自动带 source（transport 自身）；
            # 转发到上层 dispatch_core_message(message, *, source=transport)。
            await transport.start(
                lambda msg, *, source, _cb=on_message: _cb(msg, source=source)
            )
            handle = ClusterHandle(
                transport,
                cluster_id,
                spawn_materializer=self._spawn_materializer,
            )
            self._handles[cluster_id] = handle
            logger.info("ClusterTransportManager ensured cluster '%s'.", cluster_id)
            return handle

    def get_handle(self, cluster_id: str) -> ClusterHandle:
        """取已建 handle；不存在 raise KeyError。"""
        handle = self._handles.get(cluster_id)
        if handle is None:
            raise KeyError(f"cluster '{cluster_id}' not initialized")
        return handle

    def has_cluster(self, cluster_id: str) -> bool:
        return cluster_id in self._handles

    @property
    def cluster_ids(self) -> list[str]:
        return list(self._handles.keys())

    def set_on_message(self, on_message: CoreMessageHandler) -> None:
        """注入 Core 消息回调（unit init 时调用）。"""
        self._on_message = on_message

    async def shutdown_cluster(self, cluster_id: str) -> None:
        """shutdown 某 cluster：发 shutdown_cluster → 停 transport → 移除 handle。"""
        async with self._lock:
            handle = self._handles.pop(cluster_id, None)
        if handle is None:
            return
        try:
            await handle.shutdown()
        finally:
            await handle.transport.stop()
            logger.info("ClusterTransportManager shut down cluster '%s'.", cluster_id)

    async def stop(self) -> None:
        """关闭所有 handle 的 transport。"""
        async with self._lock:
            handles = list(self._handles.values())
            self._handles.clear()
        for handle in handles:
            try:
                await handle.transport.stop()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "ClusterTransportManager: stop transport for '%s' failed.",
                    handle.cluster_id,
                )


def _default_transport_factory(config: CoreTransportConfig) -> WebSocketCoreTransport:
    return WebSocketCoreTransport(config)


def _with_cluster_id(config: CoreTransportConfig, cluster_id: str) -> CoreTransportConfig:
    """复制 CoreTransportConfig 并替换 cluster_id（其余字段不变）。"""
    return CoreTransportConfig(
        url=config.url,
        reconnect_interval=config.reconnect_interval,
        max_reconnect_attempts=config.max_reconnect_attempts,
        ping_interval=config.ping_interval,
        command_timeout=config.command_timeout,
        cluster_id=cluster_id,
    )
