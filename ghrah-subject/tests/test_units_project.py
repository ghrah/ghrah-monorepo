"""Project/Recovery units 集成测试：boot 一个 full-profile engine（fake cluster transport），
验证 ProjectUnit + RecoveryUnit + DesiredStateUnit 装配、project_create 命令经 dispatcher、
reconcile bootstrap 首启建 default project。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from ghrah.subject.cluster_transport import ClusterTransportManager
from ghrah.subject.config import CoreTransportConfig, RecoveryConfig, SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import (
    CLUSTER_TRANSPORT_MANAGER,
    PROJECT_MANAGER,
    RECONCILIATION_SERVICE,
)
from ghrah.subject.transport.core import InProcessCoreTransport
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units.project import ProjectUnit
from ghrah.subject.units.recovery import DesiredStateUnit, RecoveryUnit


def _fake_transport_factory(captures: dict[str, InProcessCoreTransport]):
    def make(config: CoreTransportConfig) -> InProcessCoreTransport:
        t = _AutoRespondTransport()
        captures[config.cluster_id] = t
        return t

    return make


class _AutoRespondTransport(InProcessCoreTransport):
    """InProcessCoreTransport 变体：send_and_wait 自动回空 command_result，
    避免无真实 Core 时 list_agents/spawn_agent 永久等待。"""

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


class _FakeClusterTransportUnit(SubjectUnit):
    """ClusterTransportUnit 变体：注入 InProcessCoreTransport factory（无需真实 Core WS）。"""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._manager: ClusterTransportManager | None = None
        self._meta = UnitMeta(
            name="cluster_transport",
            provides=frozenset({CLUSTER_TRANSPORT_MANAGER}),
            routes=RouteSpec(commands=frozenset()),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> ClusterTransportManager:
        if self._manager is None:
            raise RuntimeError("not initialized")
        return self._manager

    async def init(self, ctx: Any) -> None:
        self._manager = ClusterTransportManager(
            ctx.config.core,
            on_message=lambda msg, *, source: asyncio.sleep(0),
            transport_factory=_fake_transport_factory({}),
        )
        ctx.services.set(CLUSTER_TRANSPORT_MANAGER, self._manager)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        if self._manager is not None:
            await self._manager.stop()

    async def handle_command(self, command: Any, payload: Any, cmd_ctx: Any) -> dict[str, Any]:
        return {"success": False, "data": None, "error": "no commands"}


def _build_engine(tmp_path: Path, *, recovery_enabled: bool = True) -> SubjectEngine:
    cfg = SubjectConfig(
        workspace_root=str(tmp_path / "ws"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
        recovery_slice=RecoveryConfig(
            enabled=recovery_enabled,
            reconcile_on_start=recovery_enabled,
            bootstrap_default_project=True,
        ),
    )
    engine = SubjectEngine(cfg)
    # 注册 coexistence 基础单元（含 DesiredStateUnit）
    from ghrah.subject.units import register_builtin_units

    register_builtin_units(engine, profile="coexistence")
    # 追加 full-profile 的 transport/recovery/project（用 fake cluster transport）
    # DesiredStateUnit 已由 coexistence 注册，不重复
    engine.register_unit(_FakeClusterTransportUnit(cfg))
    engine.register_unit(ProjectUnit(cfg))
    engine.register_unit(RecoveryUnit(cfg))
    return engine


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[SubjectEngine]:
    e = _build_engine(tmp_path)
    await e.start()
    try:
        yield e
    finally:
        await e.stop()


class TestUnitsAssembly:
    async def test_units_registered_and_started(self, tmp_path: Path) -> None:
        e = _build_engine(tmp_path)
        await e.start()
        try:
            assert isinstance(e.get_unit("project"), ProjectUnit)
            assert isinstance(e.get_unit("recovery"), RecoveryUnit)
            assert isinstance(e.get_unit("desired_state"), DesiredStateUnit)
            assert e.get_state("project") is not None
        finally:
            await e.stop()

    async def test_reconcile_bootstrap_creates_default_project(
        self, engine: SubjectEngine, tmp_path: Path
    ) -> None:
        # engine.start 已触发 reconcile（首启无 workspace → bootstrap）
        svc = engine.services.require(RECONCILIATION_SERVICE)
        report = await svc.reconcile_status()
        assert report is not None
        assert report.success
        assert report.bootstrap is True
        assert report.tasks_migrated == 0  # 无 sentinel task
        # default project 已创建
        project_mgr = engine.services.require(PROJECT_MANAGER)
        listed = await project_mgr.handle_command("project_list", {})
        assert listed["success"]
        assert listed["data"]["count"] == 1
        assert listed["data"]["projects"][0]["name"] == "default"

    async def test_project_create_command_via_dispatcher(
        self, engine: SubjectEngine, tmp_path: Path
    ) -> None:
        result = await engine.dispatch_observer_command(
            "project_create",
            {"name": "P2", "default_workspace_locator": f"file://{tmp_path / 'p2'}"},
        )
        assert result["success"], result.get("error")
        assert result["data"]["project"]["name"] == "P2"

    async def test_reconcile_now_command(
        self, engine: SubjectEngine
    ) -> None:
        result = await engine.dispatch_observer_command("reconcile_now", {"subject_id": "default"})
        assert result["success"]
        assert "projects_reconciled" in result["data"]

    async def test_reconcile_status_command(self, engine: SubjectEngine) -> None:
        # 先触发一次 reconcile
        await engine.dispatch_observer_command("reconcile_now", {})
        result = await engine.dispatch_observer_command("reconcile_status", {})
        assert result["success"]
        assert result["data"] is not None

    async def test_recovery_disabled_skips_reconcile(self, tmp_path: Path) -> None:
        e = _build_engine(tmp_path, recovery_enabled=False)
        await e.start()
        try:
            svc = e.services.require(RECONCILIATION_SERVICE)
            status = await svc.reconcile_status()
            # recovery disabled → engine.start 不触发 reconcile，status 为 None
            assert status is None
        finally:
            await e.stop()
