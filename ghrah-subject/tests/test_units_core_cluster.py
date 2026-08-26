# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""CoreClusterRegistry unit 测试（假 CoreUnit 工厂，无真实 Core）。

覆盖：装配与服务注册、ensure/get/shutdown 幂等、spawn 物化透传
（manifest_ref 展开为具体 abilities）、dispose 后 handle 失效、
二次 ensure 同实例。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ghrah.protocol.types import AgentConfigPayload, SpawnAgentPayload
from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.config import SubjectConfig
from ghrah.subject.core_cluster.registry import (
    CoreClusterRegistry,
)
from ghrah.subject.manifest_store.store import ManifestStore
from ghrah.subject.runtime.ouroboros_bridge import mount_unit
from ghrah.subject.runtime.service_keys import (
    CORE_CLUSTER_REGISTRY,
    MANIFEST_STORE,
    SANDBOX_EXECUTOR,
    WORKSPACE_SERVICE,
)
from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units.core_cluster import CoreClusterRegistryUnit

AGENT_YAML = """\
manifest: agent
version: "1"
metadata:
  namespace: ghrah
  name: coder
  description: A coder agent
model:
  agent_config_name: default
system_prompt: You are a coder.
max_iterations: 20
abilities:
  - type: read_file
    permissions:
      require_hitl: true
      allowed_paths:
        - "{{workspace}}/src"
  - type: conversation
"""


class _FakeCoreUnit(SubjectUnit):
    """假 CoreUnit：记录命令并返回成功回执。"""

    def __init__(self, cluster_id: str) -> None:
        self.cluster_id = cluster_id
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self.stopped = False
        self._meta = UnitMeta(
            name=f"fake-core-{cluster_id}",
            routes=RouteSpec(commands=frozenset()),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def stop(self) -> None:
        self.stopped = True

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: Any
    ) -> dict[str, Any]:
        self.commands.append((command, dict(payload)))
        if command == "list_agents":
            return {"success": True, "data": {"agents": [{"name": "coder"}]}}
        if command == "spawn_agent":
            return {"success": True, "data": {"name": payload.get("config", {}).get("name", "")}}
        return {"success": True, "data": {}}


class _FakeWorkspaceService:
    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root

    @property
    def root_path(self) -> str:
        return self._workspace_root

    async def create_workspace(self, agent_name: str) -> Any:
        return None

    def resolve_agent_path(self, agent_name: str) -> str | None:
        return str(Path(self._workspace_root) / agent_name)

    def resolve_agent_default_path(self, agent_name: str) -> str | None:
        return self.resolve_agent_path(agent_name)

    def get_workspace_record(self, workspace_id: str) -> Any | None:
        return None


def _manifest_store(tmp_path: Path) -> ManifestStore:
    store = ManifestStore(tmp_path / "manifests")
    store.ensure_dirs()
    store.put_agent("ghrah.coder", AGENT_YAML)
    return store


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def _boot(
    tmp_path: Path,
) -> tuple[Context, Any, CoreClusterRegistry, dict[str, _FakeCoreUnit]]:
    """挂载 registry unit（假工厂），返回 ctx/unit/registry/创建的假 units。"""
    created: dict[str, _FakeCoreUnit] = []

    def factory(cluster_id: str) -> _FakeCoreUnit:
        unit = _FakeCoreUnit(cluster_id)
        created.append(unit)
        return unit

    config = _config(tmp_path)
    unit = CoreClusterRegistryUnit(config, unit_factory=factory)
    workspace = _FakeWorkspaceService(str(tmp_path / "workspace"))

    ctx = await Context().__aenter__()
    try:
        ctx.provide(MANIFEST_STORE.name, _manifest_store(tmp_path))
        ctx.provide(WORKSPACE_SERVICE.name, workspace)
        ctx.provide(SANDBOX_EXECUTOR.name, SandboxExecutor(str(tmp_path / "workspace")))

        fiber = ctx.plugin(mount_unit(unit))
        await wait_active(fiber)
        registry = ctx.get(CORE_CLUSTER_REGISTRY.name)
        assert registry is unit.service
        return ctx, unit, registry, created
    except BaseException:
        await ctx.__aexit__(None, None, None)
        raise


class TestCoreClusterRegistryUnit:
    async def test_meta_shape(self, tmp_path: Path) -> None:
        unit = CoreClusterRegistryUnit(_config(tmp_path))
        assert unit.meta.name == "core_cluster_registry"
        assert unit.meta.routes.commands == frozenset()
        assert {k.name for k in unit.meta.requires} == {
            "manifest_store",
            "workspace_service",
            "sandbox_executor",
        }

    async def test_ensure_cluster_mounts_and_is_idempotent(self, tmp_path: Path) -> None:
        ctx, _, registry, created = await _boot(tmp_path)

        def by_id(cluster_id: str) -> _FakeCoreUnit:
            return next(u for u in created if u.cluster_id == cluster_id)

        try:
            assert not registry.has_cluster("default")
            handle = await registry.ensure_cluster("default")
            assert handle.is_connected
            assert registry.has_cluster("default")
            assert by_id("default").stopped is False

            # 幂等：同 cluster 返回同一 handle、不新建实例
            again = await registry.ensure_cluster("default")
            assert again is handle
            assert len(created) == 1

            # get_handle 一致；未知 cluster KeyError
            assert registry.get_handle("default") is handle
            with pytest.raises(KeyError):
                registry.get_handle("nope")
        finally:
            await registry.stop()
            await ctx.__aexit__(None, None, None)

    async def test_spawn_manifest_ref_passthrough_to_core_unit(self, tmp_path: Path) -> None:
        ctx, _, registry, created = await _boot(tmp_path)

        def by_id(cluster_id: str) -> _FakeCoreUnit:
            return next(u for u in created if u.cluster_id == cluster_id)

        try:
            handle = await registry.ensure_cluster("default")
            payload = SpawnAgentPayload(
                config=AgentConfigPayload(name="coder-1", system_prompt=""),
                manifest_ref="ghrah.coder",
            )
            result = await handle.spawn_agent(payload)
            assert result["success"], result.get("error")

            # manifest_ref 原样直通 CoreUnit（解析由 CoreUnit 内部完成，
            # 物化器已下沉 Core，handle 不再展开）
            command, sent = by_id("default").commands[-1]
            assert command == "spawn_agent"
            assert sent["manifest_ref"] == "ghrah.coder"
        finally:
            await registry.stop()
            await ctx.__aexit__(None, None, None)

    async def test_list_and_terminate_shapes(self, tmp_path: Path) -> None:
        ctx, _, registry, _ = await _boot(tmp_path)
        try:
            handle = await registry.ensure_cluster("default")
            agents = await handle.list_agents()
            assert agents == [{"name": "coder"}]
            result = await handle.terminate_agent("coder")
            assert result["success"]
        finally:
            await registry.stop()
            await ctx.__aexit__(None, None, None)

    async def test_shutdown_invalidates_handle_and_ensure_remounts(self, tmp_path: Path) -> None:
        ctx, _, registry, created = await _boot(tmp_path)

        def by_id(cluster_id: str) -> _FakeCoreUnit:
            return next(u for u in created if u.cluster_id == cluster_id)

        try:
            handle = await registry.ensure_cluster("default")
            await registry.shutdown_cluster("default")
            assert not handle.is_connected
            assert by_id("default").stopped is True
            assert not registry.has_cluster("default")

            # 关闭后命令走失败回执（不抛）
            spawn_result = await handle.spawn_agent(
                SpawnAgentPayload(config=AgentConfigPayload(name="x", system_prompt=""))
            )
            assert spawn_result["success"] is False
            assert await handle.list_agents() == []

            # 重挂：新实例
            new_handle = await registry.ensure_cluster("default")
            assert new_handle is not handle
            assert new_handle.is_connected
        finally:
            await registry.stop()
            await ctx.__aexit__(None, None, None)

    async def test_unit_stop_disposes_all_clusters(self, tmp_path: Path) -> None:
        ctx, unit, registry, created = await _boot(tmp_path)
        try:
            await registry.ensure_cluster("default")
            await registry.ensure_cluster("secondary")
            assert len(created) == 2
        finally:
            await unit.stop()
            assert not registry.has_cluster("default")
            assert not registry.has_cluster("secondary")
            assert all(u.stopped for u in created)
            await ctx.__aexit__(None, None, None)


class TestRealCoreUnitMultiCluster:
    """回归：多集群 = 多真实 CoreUnit 实例共存。

    历史盲区：本文件其他用例全部走 _FakeCoreUnit 工厂，从不触达真实
    CoreUnit.init——provide("supervisor") 时代第二个实例挂载即
    ServiceConflictError（Ouroboros 同名服务全局唯一）。provide 删除后
    每实例状态自持，多实例天然隔离。
    """

    async def test_two_real_core_units_coexist_and_isolate(self, tmp_path: Path) -> None:
        from ghrah.core.unit import CoreUnitConfig, create_core_unit

        def factory(cluster_id: str, project_root_locator: str = "") -> Any:
            return create_core_unit(CoreUnitConfig(cluster_id=cluster_id))

        config = _config(tmp_path)
        unit = CoreClusterRegistryUnit(config, unit_factory=factory)
        workspace = _FakeWorkspaceService(str(tmp_path / "workspace"))

        ctx = await Context().__aenter__()
        try:
            ctx.provide(MANIFEST_STORE.name, _manifest_store(tmp_path))
            ctx.provide(WORKSPACE_SERVICE.name, workspace)
            ctx.provide(SANDBOX_EXECUTOR.name, SandboxExecutor(str(tmp_path / "workspace")))

            fiber = ctx.plugin(mount_unit(unit))
            await wait_active(fiber)
            registry = ctx.get(CORE_CLUSTER_REGISTRY.name)

            # 两个真实 CoreUnit 实例挂载不冲突（provide 删除前必炸）
            handle_a = await registry.ensure_cluster("alpha")
            handle_b = await registry.ensure_cluster("beta")
            assert handle_a.is_connected and handle_b.is_connected

            spawn_a = await handle_a.spawn_agent(
                SpawnAgentPayload(
                    config=AgentConfigPayload(name="agent-a", system_prompt="x")
                )
            )
            assert spawn_a["success"], spawn_a.get("error")
            spawn_b = await handle_b.spawn_agent(
                SpawnAgentPayload(
                    config=AgentConfigPayload(name="agent-b", system_prompt="x")
                )
            )
            assert spawn_b["success"], spawn_b.get("error")

            # agent 列表按实例隔离
            assert [a["name"] for a in await handle_a.list_agents()] == ["agent-a"]
            assert [a["name"] for a in await handle_b.list_agents()] == ["agent-b"]
        finally:
            await registry.stop()
            await ctx.__aexit__(None, None, None)
