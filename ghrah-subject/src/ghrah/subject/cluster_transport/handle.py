# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ClusterHandle：单 cluster 的 Core 接入封装。

每个 :class:`ClusterHandle` 包裹一条 :class:`WebSocketCoreTransport`（该
cluster 专属 WS），转发 Core 集群命令（spawn_agent / list_agents /
terminate_agent / shutdown_cluster）。命令经 ``send_and_wait`` 取
``command_result`` 回执（与 Core 现有 router.send_and_wait 协议一致）；
init_cluster 由 transport 连接建立时自动 fire-and-forget 发送（幂等重绑定）。

    本类为 :mod:`ghrah.subject.cluster_transport.manager` 的内部协作件，亦作为
    ``ClusterHandle`` service Protocol 的具体实现。

    D3 物化：可选注入 ``spawn_materializer``（由 ClusterTransportManager 透传）。
    ``spawn_agent`` 在 ``send_and_wait`` 前对带 ``manifest_ref`` 的 payload 先经
    物化器展开，物化后 ``manifest_ref`` 置 None、``abilities`` 填充。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ghrah.protocol.types import (
    SpawnAgentPayload,
    TerminateAgentPayload,
    generate_request_id,
)
from ghrah.subject.transport.core import CoreMessage, CoreTransport

__all__ = ["ClusterHandle", "SpawnMaterializer"]

SpawnMaterializer = Callable[[SpawnAgentPayload], SpawnAgentPayload]


class ClusterHandle:
    """单 cluster 的 Core 命令转发封装。

    Attributes:
        transport: 该 cluster 专属的 transport（WebSocketCoreTransport 或测试
            fake，满足 CoreTransport Protocol）。
        cluster_id: 该 handle 持有的 Core 集群 id。
    """

    def __init__(
        self,
        transport: CoreTransport,
        cluster_id: str,
        *,
        spawn_materializer: SpawnMaterializer | None = None,
    ) -> None:
        self._transport = transport
        self._cluster_id = cluster_id
        self._spawn_materializer = spawn_materializer

    @property
    def cluster_id(self) -> str:
        return self._cluster_id

    @property
    def transport(self) -> CoreTransport:
        return self._transport

    @property
    def is_connected(self) -> bool:
        """该 handle 的 transport 是否已连接。"""
        return self._transport.is_connected

    async def spawn_agent(self, payload: SpawnAgentPayload) -> dict[str, Any]:
        """经该 cluster WS 发 spawn_agent，等待 command_result 回执。

        若注入了 ``spawn_materializer`` 且 ``payload.manifest_ref`` 存在，先经
        物化器展开 manifest 为具体 abilities（D3），再发送。

        Returns:
            ``{"success": bool, "data": ..., "error": str | None}`` 形态 dict。
        """
        if self._spawn_materializer is not None and payload.manifest_ref:
            payload = self._spawn_materializer(payload)
        message: CoreMessage = {
            "type": "spawn_agent",
            "payload": payload.model_dump(mode="json"),
            "request_id": generate_request_id(),
        }
        result = await self._transport.send_and_wait(message)
        return _parse_command_result(result)

    async def list_agents(self) -> list[dict[str, Any]]:
        """经该 cluster WS 发 list_agents，返回 agent 信息列表。"""
        message: CoreMessage = {
            "type": "list_agents",
            "payload": {},
            "request_id": generate_request_id(),
        }
        result = await self._transport.send_and_wait(message)
        parsed = _parse_command_result(result)
        if not parsed["success"]:
            return []
        data = parsed["data"]
        if isinstance(data, list):
            return [a for a in data if isinstance(a, dict)]
        if isinstance(data, dict):
            agents = data.get("agents")
            if isinstance(agents, list):
                return [a for a in agents if isinstance(a, dict)]
        return []

    async def terminate_agent(self, agent_name: str) -> dict[str, Any]:
        """经该 cluster WS 发 terminate_agent，等待 command_result 回执。"""
        message: CoreMessage = {
            "type": "terminate_agent",
            "payload": TerminateAgentPayload(name=agent_name).model_dump(mode="json"),
            "request_id": generate_request_id(),
        }
        result = await self._transport.send_and_wait(message)
        return _parse_command_result(result)

    async def shutdown(self) -> None:
        """fire-and-forget 发 shutdown_cluster（不等待回执）。

        cluster 实际关闭由 Core 侧 supervisor 销毁；transport 连接随后断开。
        """
        message: CoreMessage = {
            "type": "shutdown_cluster",
            "payload": {"cluster_id": self._cluster_id},
            "request_id": generate_request_id(),
        }
        try:
            await self._transport.send(message)
        except Exception:  # noqa: BLE001 — 关闭路径不阻断
            pass


def _parse_command_result(result: CoreMessage) -> dict[str, Any]:
    """从 command_result 提取 success/data/error。

    ``send_and_wait`` 经 dispatcher 回调 ``resolve_command_result(request_id, payload)``
    resolve，故 ``result`` 通常已是内层 payload（``{"success": ..., "data": ...,
    "error": ...}``）。兼容直接以整条 command_result envelope（``{"type":
    "command_result", "payload": {...}, "request_id": ...}``）调用
    ``resolve_command_result`` 的旧路径：若 ``result`` 含 ``payload`` dict 则从中提取。
    """
    payload = result.get("payload") if isinstance(result, dict) else None
    if isinstance(payload, dict):
        source = payload
    elif isinstance(result, dict) and "success" in result:
        source = result
    else:
        return {"success": False, "data": None, "error": "invalid command_result payload"}
    return {
        "success": bool(source.get("success", False)),
        "data": source.get("data"),
        "error": source.get("error"),
    }
