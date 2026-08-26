# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""CoreClusterRegistry — cluster = CoreUnit 实例（进程内注册表）。

取代旧 ``ClusterTransportManager``（per-cluster WS transport 句柄管理）：
``ensure_cluster(cluster_id)`` 在 Ouroboros ctx 上**运行时挂载**一个
CoreUnit 实例（``ctx.plugin(mount_unit(unit))``，热插拔 API 的首个真实
消费者）；``shutdown_cluster`` → ``fiber.dispose()``。多集群 = 多实例
（MVP 单集群——Ouroboros 同名 service 二次 provide 会 ServiceConflictError，
多实例需 CoreUnitConfig.service_prefix，见计划开放问题）。

``CoreUnitHandle`` duck-type 现有 ``ClusterHandle`` 消费面
（spawn_agent/list_agents/terminate_agent/is_connected），命令经
``unit.handle_command`` 进程内直达 CoreUnit。manifest_ref 的解析/物化
由 CoreUnit 内部完成（对齐 Core 独立库 runner 范式，不经 wire DTO 往返）；
subject 仅注入 ManifestStore（``CoreUnitConfig.manifest_store``）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ghrah.protocol.types import (
    SpawnAgentPayload,
    TerminateAgentPayload,
)
from ghrah.subject.runtime.ouroboros_bridge import mount_unit, wait_active
from ghrah.subject.unit.base import CommandContext

if TYPE_CHECKING:
    from ouroboros import Context, Fiber  # type: ignore[import-untyped]

    from ghrah.subject.config import SubjectConfig

__all__ = [
    "CoreClusterRegistry",
    "CoreUnitHandle",
    "default_core_unit_factory",
]

logger = logging.getLogger(__name__)

_INTERNAL_CMD_CTX = CommandContext.internal()


class CoreUnitHandle:
    """单 cluster 的 Core 接入门面（ClusterHandle duck-type，进程内直达）。

    is_connected = 实例已挂载且未被 shutdown；关闭后命令返回 failure dict
    （对齐旧 transport 断连时的回执语义，消费者只看 ``success``）。
    """

    def __init__(
        self,
        registry: CoreClusterRegistry,
        cluster_id: str,
        unit: Any,
    ) -> None:
        self._registry = registry
        self._cluster_id = cluster_id
        self._unit = unit
        self._alive = True

    @property
    def cluster_id(self) -> str:
        return self._cluster_id

    @property
    def is_connected(self) -> bool:
        """该 cluster 的 CoreUnit 实例是否仍在运行。"""
        return self._alive

    async def spawn_agent(self, payload: SpawnAgentPayload) -> dict[str, Any]:
        """经进程内 CoreUnit 发 spawn_agent（manifest_ref 由 CoreUnit 内部解析）。"""
        if not self._alive:
            return {"success": False, "error": f"cluster '{self._cluster_id}' is shut down"}
        return await self._dispatch("spawn_agent", payload.model_dump(mode="json"))

    async def list_agents(self) -> list[dict[str, Any]]:
        """经进程内 CoreUnit 发 list_agents，返回 agent 信息列表。"""
        if not self._alive:
            return []
        result = await self._dispatch("list_agents", {})
        if not result.get("success"):
            return []
        data = result.get("data")
        if isinstance(data, list):
            return [a for a in data if isinstance(a, dict)]
        if isinstance(data, dict):
            agents = data.get("agents")
            if isinstance(agents, list):
                return [a for a in agents if isinstance(a, dict)]
        return []

    async def terminate_agent(self, agent_name: str) -> dict[str, Any]:
        """经进程内 CoreUnit 发 terminate_agent，返回回执 dict。"""
        if not self._alive:
            return {"success": False, "error": f"cluster '{self._cluster_id}' is shut down"}
        payload = TerminateAgentPayload(name=agent_name).model_dump(mode="json")
        return await self._dispatch("terminate_agent", payload)

    async def shutdown(self) -> None:
        """关闭该 cluster（dispose CoreUnit fiber，幂等）。"""
        await self._registry.shutdown_cluster(self._cluster_id)

    async def _dispatch(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self._unit.handle_command(command, payload, _INTERNAL_CMD_CTX)
        if not isinstance(result, dict):
            return {"success": False, "error": f"Unexpected result for {command}"}
        return result


class _ClusterEntry:
    """一个已挂载 cluster 的登记项。"""

    __slots__ = ("fiber", "handle", "unit")

    def __init__(self, unit: Any, fiber: Fiber, handle: CoreUnitHandle) -> None:
        self.unit = unit
        self.fiber = fiber
        self.handle = handle


class CoreClusterRegistry:
    """cluster → CoreUnit 实例注册表（ensure/get/shutdown，幂等）。

    ``unit_factory: (cluster_id) -> unit``（duck-typed，默认
    ``default_core_unit_factory``；测试注入假工厂）。
    """

    def __init__(
        self,
        *,
        unit_factory: Callable[[str], Any],
    ) -> None:
        self._unit_factory = unit_factory
        self._ctx: Context | None = None
        self._clusters: dict[str, _ClusterEntry] = {}

    def bind(self, ctx: Context) -> None:
        """绑定宿主 ctx（unit.init 时调用；运行时挂载经它 ctx.plugin）。"""
        self._ctx = ctx

    @property
    def cluster_ids(self) -> list[str]:
        return list(self._clusters)

    async def ensure_cluster(self, cluster_id: str) -> CoreUnitHandle:
        """幂等挂载/取某 cluster 的 CoreUnit 实例。"""
        entry = self._clusters.get(cluster_id)
        if entry is not None:
            return entry.handle
        if self._ctx is None:
            raise RuntimeError("CoreClusterRegistry has not been bound to a Context.")

        unit = self._unit_factory(cluster_id)
        fiber = self._ctx.plugin(mount_unit(unit))
        await wait_active(fiber, timeout=10.0)
        handle = CoreUnitHandle(self, cluster_id, unit)
        self._clusters[cluster_id] = _ClusterEntry(unit, fiber, handle)
        logger.info("CoreClusterRegistry: mounted cluster '%s'", cluster_id)
        return handle

    def get_handle(self, cluster_id: str) -> CoreUnitHandle:
        """取已挂载 handle；不存在 raise KeyError。"""
        entry = self._clusters.get(cluster_id)
        if entry is None:
            raise KeyError(cluster_id)
        return entry.handle

    def has_cluster(self, cluster_id: str) -> bool:
        return cluster_id in self._clusters

    async def shutdown_cluster(self, cluster_id: str) -> None:
        """dispose 某 cluster 的 fiber（handle 失效，幂等）。"""
        entry = self._clusters.pop(cluster_id, None)
        if entry is None:
            return
        entry.handle._alive = False
        await entry.fiber.dispose()
        logger.info("CoreClusterRegistry: disposed cluster '%s'", cluster_id)

    async def stop(self) -> None:
        """关闭全部 cluster（unit.stop 时调用，幂等）。"""
        for cluster_id in list(self._clusters):
            await self.shutdown_cluster(cluster_id)


def default_core_unit_factory(
    config: SubjectConfig,
    manifest_store: Any = None,
) -> Callable[[str], Any]:
    """生产工厂：cluster_id → CoreUnit（CoreUnitConfig 从 SubjectConfig 派生）。

    persistence_factory 注入 Core sqlite（``core_db_path``，与 ledger 读侧
    同源派生）——agent 链真相源落 Core 内建 backend（聚合裁决 D-C）。

    ``manifest_store`` 注入 CoreUnitConfig.manifest_store，供 CoreUnit 内部
    解析 manifest_ref spawn（对齐 Core 独立库 runner 范式）。由
    ``CoreClusterRegistryUnit.init`` 从 ctx 取 ``MANIFEST_STORE`` 后传入
    （挂载顺序保证 store 先于 CoreUnit，见 mount_builtin_units）。
    """
    from ghrah.context.persistence.sqlite_backend import (  # type: ignore[import-untyped]
        SqliteBackend,
    )
    from ghrah.core.unit import (  # type: ignore[import-untyped]
        CoreUnitConfig,
        create_core_unit,
    )

    core_db_path = config.core_db_path

    def persistence_factory(agent_config: Any) -> Any:
        return SqliteBackend(db_path=core_db_path)

    def factory(cluster_id: str) -> Any:
        core_config = CoreUnitConfig(
            cluster_id=cluster_id,
            hitl_timeout=config.core.command_timeout,
            workspace_root=config.workspace_root,
            auto_approve_abilities=tuple(config.hitl_policy.auto_approve_abilities),
            require_approval_by_default=config.hitl_policy.require_approval_by_default,
            persistence_factory=persistence_factory,
            manifest_store=manifest_store,
        )
        return create_core_unit(core_config)

    return factory
