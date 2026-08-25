# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Core cluster registry built-in Subject unit.

持有 :class:`CoreClusterRegistry`（cluster = CoreUnit 实例注册表，进程内
运行时挂载），提供 ``CORE_CLUSTER_REGISTRY`` 服务。``project`` /
``recovery`` 经其 ensure/get handle 消费 spawn/list/terminate/shutdown
语义（对齐旧 CLUSTER_TRANSPORT_MANAGER 消费面，零改动平移）。

``init`` 经 ctx 取 ``MANIFEST_STORE`` + ``WORKSPACE_SERVICE`` 构造 spawn
物化器（manifest_ref 展开 + 权限物化），随 registry 注入 handle。
无命令路由（cluster 命令 = registry 操作，经 project/recovery 消费）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.core_cluster.registry import (
    CoreClusterRegistry,
    build_spawn_materializer,
    default_core_unit_factory,
)
from ghrah.subject.runtime.service_keys import (
    CORE_CLUSTER_REGISTRY,
    MANIFEST_STORE,
    SANDBOX_EXECUTOR,
    WORKSPACE_SERVICE,
)
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta

__all__ = ["CoreClusterRegistryUnit"]


class CoreClusterRegistryUnit(SubjectUnit):
    """Provides the CORE_CLUSTER_REGISTRY service (cluster = CoreUnit 实例)."""

    def __init__(
        self,
        config: SubjectConfig,
        *,
        unit_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._config = config
        self._unit_factory = unit_factory or default_core_unit_factory(config)
        self._registry: CoreClusterRegistry | None = None
        self._meta = UnitMeta(
            name="core_cluster_registry",
            requires=frozenset({MANIFEST_STORE, WORKSPACE_SERVICE, SANDBOX_EXECUTOR}),
            provides=frozenset({CORE_CLUSTER_REGISTRY}),
            routes=RouteSpec(commands=frozenset()),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> CoreClusterRegistry:
        if self._registry is None:
            raise RuntimeError("CoreClusterRegistryUnit has not been initialized.")
        return self._registry

    async def init(self, ctx: Any) -> None:
        store = ctx.get(MANIFEST_STORE.name)
        workspace = ctx.get(WORKSPACE_SERVICE.name)
        registry = CoreClusterRegistry(
            unit_factory=self._unit_factory,
            spawn_materializer=build_spawn_materializer(store, workspace),
        )
        registry.bind(ctx)
        self._registry = registry
        ctx.provide(CORE_CLUSTER_REGISTRY.name, registry)

    async def start(self) -> None:
        # CoreUnit 实例按需懒挂载（ensure_cluster），无启动期动作。
        pass

    async def stop(self) -> None:
        if self._registry is not None:
            await self._registry.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        return {"success": False, "data": None, "error": "core_cluster_registry has no commands"}
