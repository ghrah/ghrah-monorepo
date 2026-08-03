# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Cluster transport built-in Subject unit.

Owns :class:`ClusterTransportManager`（per-cluster WS transport 句柄管理，决策 A）
并把它注册为 ``CLUSTER_TRANSPORT_MANAGER`` service。

``init`` 阶段从 ctx.services 取 ``MANIFEST_STORE`` + ``WORKSPACE_SERVICE`` 构造
``spawn_materializer``，注入 manager（→ handle），使 ``ClusterHandle.spawn_agent``
自动展开 ``manifest_ref``（D3 物化）。
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from ghrah.manifest.resolver import ManifestResolver  # type: ignore[import-untyped]
from ghrah.protocol.types import (
    AbilityDefinitionPayload,
    AgentConfigPayload,
    SpawnAgentPayload,
)
from ghrah.subject.cluster_transport.handle import SpawnMaterializer
from ghrah.subject.cluster_transport.manager import ClusterTransportManager
from ghrah.subject.config import SubjectConfig
from ghrah.subject.manifest_store.store import ManifestStore
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import (
    CLUSTER_TRANSPORT_MANAGER,
    MANIFEST_STORE,
    WORKSPACE_SERVICE,
)
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._helpers import materialize_permission_params

__all__ = ["ClusterTransportUnit"]

logger = logging.getLogger(__name__)


class ClusterTransportUnit(SubjectUnit):
    """Provides the CLUSTER_TRANSPORT_MANAGER service.

    无命令路由（cluster 命令转发由 ProjectManager / ReconciliationService 经
    ClusterHandle 直接发，不经 dispatcher）。requires ``MANIFEST_STORE`` +
    ``WORKSPACE_SERVICE`` 以在 ``init`` 构造 spawn 物化器（拓扑排序保证其就位）。
    on_message 回调在 start() 注入（dispatcher 就绪后）。
    """

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ctx: SubjectContext | None = None
        self._manager: ClusterTransportManager | None = None
        self._meta = UnitMeta(
            name="cluster_transport",
            provides=frozenset({CLUSTER_TRANSPORT_MANAGER}),
            requires=frozenset({MANIFEST_STORE, WORKSPACE_SERVICE}),
            routes=RouteSpec(commands=frozenset()),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> ClusterTransportManager:
        if self._manager is None:
            raise RuntimeError("ClusterTransportUnit has not been initialized.")
        return self._manager

    async def init(self, ctx: SubjectContext) -> None:
        self._ctx = ctx
        store = ctx.services.require(MANIFEST_STORE)
        workspace = ctx.services.require(WORKSPACE_SERVICE)
        materializer = _build_spawn_materializer(store, workspace)
        self._manager = ClusterTransportManager(
            ctx.config.core,
            spawn_materializer=materializer,
        )
        ctx.services.set(CLUSTER_TRANSPORT_MANAGER, self._manager)

    async def start(self) -> None:
        if self._manager is None or self._ctx is None:
            raise RuntimeError("ClusterTransportUnit has not been initialized.")
        self._manager.set_on_message(self._ctx.dispatcher.dispatch_core_message)

    async def stop(self) -> None:
        if self._manager is not None:
            await self._manager.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: Any,
    ) -> dict[str, Any]:
        return {"success": False, "data": None, "error": "cluster_transport has no commands"}


def _build_spawn_materializer(
    store: ManifestStore, workspace: Any
) -> SpawnMaterializer:
    """构造 spawn 物化器（D3）。

    平移自 ``units/forward.py:_resolve_spawn_manifest``，把依赖从
    ``ctx.services.require`` 改为构造期捕获的 ``store``/``workspace``。返回
    ``SpawnMaterializer``：输入带 ``manifest_ref`` 的 payload，输出展开后的
    ``SpawnAgentPayload``（manifest_ref 置 None、abilities 填充、config 从解析结果重建）。
    """

    def materialize(payload: SpawnAgentPayload) -> SpawnAgentPayload:
        manifest_ref = payload.manifest_ref
        if not manifest_ref:
            return payload
        runtime_name = payload.config.name or None
        manifest = store.get_agent(manifest_ref)
        resolved = ManifestResolver(store).resolve(manifest, runtime_name=runtime_name)
        workspace_root = workspace.resolve_agent_path(resolved.config.name)

        expanded_abilities: list[AbilityDefinitionPayload] = []
        for ability in resolved.abilities:
            implementation = ability.implementation
            if implementation.type == "builtin" and implementation.handler:
                expanded_abilities.append(
                    AbilityDefinitionPayload(
                        ability_type=implementation.handler,
                        params=materialize_permission_params(
                            implementation.handler,
                            ability.permissions,
                            workspace_root,
                        ),
                    )
                )
                continue
            logger.warning(
                "Skipping non-builtin ability '%s' (type=%s) in manifest spawn",
                ability.ability_name,
                implementation.type,
            )

        return SpawnAgentPayload(
            config=_agent_config_to_payload(resolved.config),
            abilities=expanded_abilities if expanded_abilities else None,
            manifest_ref=None,
        )

    return materialize


def _agent_config_to_payload(config: Any) -> AgentConfigPayload:
    """从解析后的 ``AgentConfig`` 构造 ``AgentConfigPayload``（对齐 forward 旧实现）。"""
    return AgentConfigPayload(
        name=config.name,
        agent_config_name=config.agent_config_name,
        description=config.description,
        system_prompt=config.system_prompt,
        max_iterations=config.max_iterations,
        communication_timeout=config.communication_timeout,
        window=dataclasses.asdict(config.window) if config.window else None,
        context=dataclasses.asdict(config.context) if config.context else None,
        model_overrides=(
            dataclasses.asdict(config.model_overrides)
            if config.model_overrides
            else None
        ),
    )
