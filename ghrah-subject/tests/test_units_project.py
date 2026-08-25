"""Project/Recovery units 集成测试（Ouroboros 形态）：coexistence 工厂 +
fake cluster transport（root provide）+ ProjectUnit/RecoveryUnit 挂载，
验证装配、project_create 命令经 ctx.serial 路由、reconcile bootstrap。

与旧基建形态的差异：mount 不自动触发 reconcile（原 engine.start 末尾触发，
归阶段 3.4 装配层）；本文件显式调 ``svc.reconcile()`` 验证 bootstrap 语义。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from ouroboros import Context, Fiber  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.cluster_transport import ClusterTransportManager
from ghrah.subject.config import CoreTransportConfig, RecoveryConfig, SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_unit
from ghrah.subject.runtime.service_keys import (
    CLUSTER_TRANSPORT_MANAGER,
    PROJECT_MANAGER,
    RECONCILIATION_SERVICE,
)
from ghrah.subject.transport.core import InProcessCoreTransport
from ghrah.subject.units import mount_builtin_units
from ghrah.subject.units.project import ProjectUnit
from ghrah.subject.units.recovery import RecoveryUnit


def _fake_transport_factory(captures: dict[str, InProcessCoreTransport]):
    def make(config: CoreTransportConfig) -> InProcessCoreTransport:
        t = _AutoRespondTransport()
        captures[config.cluster_id] = t
        return t

    return make


class _AutoRespondTransport(InProcessCoreTransport):
    """InProcessCoreTransport 变体：send_and_wait 自动回空 command_result，
    避免无真实 Core 时 list_agents/spawn_agent 永久等待。
    """

    async def send_and_wait(self, message, timeout=None):  # type: ignore[no-untyped-def]
        request_id = message.get("request_id") or "auto"
        msg_type = message.get("type", "")
        # list_agents → 空 agent 列表；spawn_agent → success；其余 → success
        if msg_type == "list_agents":
            data: list[dict[str, Any]] = []
        elif msg_type == "spawn_agent":
            data = {"name": message.get("payload", {}).get("config", {}).get("name", "")}
        else:
            data = {}
        return {
            "type": "command_result",
            "payload": {"success": True, "data": data, "error": None},
            "request_id": request_id,
        }


def _config(tmp_path: Path, *, recovery_enabled: bool = True) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "ws"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
        recovery_slice=RecoveryConfig(
            enabled=recovery_enabled,
            reconcile_on_start=recovery_enabled,
            bootstrap_default_project=True,
        ),
    )


@asynccontextmanager
async def _boot(
    tmp_path: Path, *, recovery_enabled: bool = True
) -> AsyncIterator[tuple[Context, dict[str, Fiber], ClusterTransportManager]]:
    config = _config(tmp_path, recovery_enabled=recovery_enabled)
    async with Context() as ctx:
        # fake cluster transport：root provide（cluster_transport unit 归项①）
        manager = ClusterTransportManager(
            config.core,
            on_message=lambda msg, *, source: asyncio.sleep(0),
            transport_factory=_fake_transport_factory({}),
        )
        ctx.provide(CLUSTER_TRANSPORT_MANAGER.name, manager)

        fibers = await mount_builtin_units(ctx, config, profile="coexistence")
        # project/recovery 逐个挂载等 ACTIVE（对齐工厂顺序语义）
        fibers["project"] = ctx.plugin(mount_unit(ProjectUnit(config)))
        await wait_active(fibers["project"])
        fibers["recovery"] = ctx.plugin(mount_unit(RecoveryUnit(config)))
        await wait_active(fibers["recovery"])
        try:
            yield ctx, fibers, manager
        finally:
            await manager.stop()


class TestUnitsAssembly:
    async def test_units_registered_and_started(self, tmp_path: Path) -> None:
        async with _boot(tmp_path) as (_, fibers, _):
            assert "project" in fibers
            assert "recovery" in fibers
            assert fibers["project"].state.value == "active"
            assert fibers["recovery"].state.value == "active"

    async def test_reconcile_bootstrap_creates_default_project(
        self, tmp_path: Path
    ) -> None:
        async with _boot(tmp_path) as (ctx, _, _):
            svc = ctx.get(RECONCILIATION_SERVICE.name)
            # 显式触发首启 reconcile（自动触发归阶段 3.4）：无 workspace → bootstrap
            report = await svc.reconcile()
            assert report.success
            assert report.bootstrap is True
            assert report.tasks_migrated == 0  # 无 sentinel task
            # default project 已创建
            project_mgr = ctx.get(PROJECT_MANAGER.name)
            listed = await project_mgr.handle_command("project_list", {})
            assert listed["success"]
            assert listed["data"]["count"] == 1
            assert listed["data"]["projects"][0]["name"] == "default"

    async def test_project_create_command_via_dispatcher(
        self, tmp_path: Path
    ) -> None:
        async with _boot(tmp_path) as (ctx, _, _):
            result = await bridge_command(
                ctx,
                "project_create",
                {"name": "P2", "default_workspace_locator": f"file://{tmp_path / 'p2'}"},
            )
            assert result["success"], result.get("error")
            assert result["data"]["project"]["name"] == "P2"

    async def test_reconcile_now_command(self, tmp_path: Path) -> None:
        async with _boot(tmp_path) as (ctx, _, _):
            result = await bridge_command(
                ctx, "reconcile_now", {"subject_id": "default"}
            )
            assert result["success"]
            assert "projects_reconciled" in result["data"]

    async def test_reconcile_status_command(self, tmp_path: Path) -> None:
        async with _boot(tmp_path) as (ctx, _, _):
            # 先触发一次 reconcile
            await bridge_command(ctx, "reconcile_now", {})
            result = await bridge_command(ctx, "reconcile_status", {})
            assert result["success"]
            assert result["data"] is not None

    async def test_recovery_disabled_skips_reconcile(self, tmp_path: Path) -> None:
        async with _boot(tmp_path, recovery_enabled=False) as (ctx, _, _):
            svc = ctx.get(RECONCILIATION_SERVICE.name)
            status = await svc.reconcile_status()
            # mount 不自动 reconcile（原 engine.start 触发，归阶段 3.4）→ 无痕迹
            assert status is None
