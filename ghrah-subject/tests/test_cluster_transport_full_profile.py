"""Full-profile engine 集成测试：fake WS connection factory 让 ``WebSocketCoreConnection``
真实走 connect/receive/init_cluster 路径，验证 cluster transport 重构后的关键不变量
（无双绑、幂等 ensure_cluster、bootstrap default project、多 cluster 各一条 WS、
command_result 经 source transport 正确 resolve）。

与 ``test_units_project.py`` 互补：后者用 ``InProcessCoreTransport`` 回避真实 WS；
本测试用真实 ``WebSocketCoreTransport`` + fake ``connect_factory``（注入 ``_FakeWS``）。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from ghrah.protocol.types import AgentConfigPayload, SpawnAgentPayload

from ghrah.subject.cluster_transport import ClusterTransportManager
from ghrah.subject.config import CoreTransportConfig, RecoveryConfig, SubjectConfig
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import (
    CLUSTER_TRANSPORT_MANAGER,
    MANIFEST_STORE,
    PROJECT_MANAGER,
    WORKSPACE_SERVICE,
)
from ghrah.subject.transport.core import WebSocketCoreTransport
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units.cluster_transport import _build_spawn_materializer
from ghrah.subject.units.project import ProjectUnit
from ghrah.subject.units.recovery import RecoveryUnit

_END = object()


class _FakeWS:
    """模拟 websockets 连接：sent 记录出站，incoming 提供入站消息流。"""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.incoming: asyncio.Queue[Any] = asyncio.Queue()
        self._responder_task: asyncio.Task[None] | None = None

    def __aiter__(self) -> _FakeWS:
        return self

    async def __anext__(self) -> Any:
        item = await self.incoming.get()
        if item is _END:
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            raise item
        return item

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    async def finish(self) -> None:
        await self.incoming.put(_END)

    def start_auto_responder(self) -> None:
        self._responder_task = asyncio.create_task(self._auto_respond())

    async def _auto_respond(self) -> None:
        """对出站命令自动回灌 command_result（bootstrap list_agents / spawn_agent）。"""
        seen = 0
        while True:
            await asyncio.sleep(0)
            while seen < len(self.sent):
                raw = self.sent[seen]
                seen += 1
                msg = json.loads(raw)
                request_id = msg.get("request_id")
                if request_id is None:
                    continue
                msg_type = msg.get("type")
                if msg_type == "list_agents":
                    data: Any = []
                elif msg_type == "spawn_agent":
                    data = {"name": msg.get("payload", {}).get("config", {}).get("name", "")}
                elif msg_type in {"shutdown_cluster", "init_cluster"}:
                    continue  # fire-and-forget
                else:
                    data = {}
                await self.incoming.put(
                    json.dumps(
                        {
                            "type": "command_result",
                            "payload": {"success": True, "data": data, "error": None},
                            "request_id": request_id,
                        }
                    )
                )

    async def stop_responder(self) -> None:
        if self._responder_task is not None:
            self._responder_task.cancel()
            try:
                await self._responder_task
            except asyncio.CancelledError:
                pass
            self._responder_task = None


class _FakeWSClusterTransportUnit(SubjectUnit):
    """ClusterTransportUnit 变体：transport_factory 用真实 WebSocketCoreTransport +
    fake connect_factory（注入 _FakeWS），真实走 connect/receive/init_cluster。
    物化器构造与真实 unit 一致（经 _build_spawn_materializer）。"""

    def __init__(self, config: SubjectConfig, ws_captures: dict[str, _FakeWS]) -> None:
        self._config = config
        self._ws_captures = ws_captures
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
            raise RuntimeError("not initialized")
        return self._manager

    async def init(self, ctx: SubjectContext) -> None:
        self._ctx = ctx
        store = ctx.services.require(MANIFEST_STORE)
        workspace = ctx.services.require(WORKSPACE_SERVICE)
        materializer = _build_spawn_materializer(store, workspace)
        captures = self._ws_captures

        def transport_factory(cfg: CoreTransportConfig) -> WebSocketCoreTransport:
            async def connect(url: str, **kwargs: Any) -> _FakeWS:
                del url, kwargs
                ws = _FakeWS()
                ws.start_auto_responder()
                captures[cfg.cluster_id] = ws
                return ws

            async def sleep(delay: float) -> None:
                del delay

            return WebSocketCoreTransport(
                cfg,
                connect_factory=connect,
                sleep=sleep,
            )

        self._manager = ClusterTransportManager(
            ctx.config.core,
            transport_factory=transport_factory,
            spawn_materializer=materializer,
        )
        ctx.services.set(CLUSTER_TRANSPORT_MANAGER, self._manager)

    async def start(self) -> None:
        if self._manager is None or self._ctx is None:
            raise RuntimeError("not initialized")
        self._manager.set_on_message(self._ctx.dispatcher.dispatch_core_message)

    async def stop(self) -> None:
        if self._manager is not None:
            await self._manager.stop()


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "ws"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
        recovery_slice=RecoveryConfig(
            enabled=True,
            reconcile_on_start=True,
            bootstrap_default_project=True,
        ),
    )


def _build_engine(tmp_path: Path) -> tuple[SubjectEngine, dict[str, _FakeWS]]:
    cfg = _config(tmp_path)
    ws_captures: dict[str, _FakeWS] = {}
    engine = SubjectEngine(cfg)
    from ghrah.subject.units import register_builtin_units

    register_builtin_units(engine, profile="coexistence")
    # coexistence 已注册 WorkspaceUnit（provides WORKSPACE_SERVICE/WORKSPACE_MANAGER）与
    # ManifestStoreUnit。追加 full-profile 单元（用 fake-WS cluster transport unit）。
    engine.register_unit(_FakeWSClusterTransportUnit(cfg, ws_captures))
    engine.register_unit(ProjectUnit(cfg))
    engine.register_unit(RecoveryUnit(cfg))
    return engine, ws_captures


@pytest.fixture
async def engine_and_ws(
    tmp_path: Path,
) -> AsyncIterator[tuple[SubjectEngine, dict[str, _FakeWS]]]:
    e, ws_captures = _build_engine(tmp_path)
    await e.start()
    try:
        yield e, ws_captures
    finally:
        await e.stop()


class TestFullProfileClusterTransport:
    async def test_only_one_default_ws_no_double_bind(
        self,
        engine_and_ws: tuple[SubjectEngine, dict[str, _FakeWS]],
    ) -> None:
        e, ws_captures = engine_and_ws
        # bootstrap default project → ensure_cluster("default") → 仅一条 default WS
        assert "default" in ws_captures
        assert len(ws_captures) == 1
        ws = ws_captures["default"]
        # 连接成功后首条出站为 init_cluster(cluster_id=default)
        first = json.loads(ws.sent[0])
        assert first["type"] == "init_cluster"
        assert first["payload"] == {"cluster_id": "default"}

    async def test_ensure_cluster_default_idempotent_no_reconnect(
        self,
        engine_and_ws: tuple[SubjectEngine, dict[str, _FakeWS]],
    ) -> None:
        e, ws_captures = engine_and_ws
        mgr = e.services.require(CLUSTER_TRANSPORT_MANAGER)
        h1 = await mgr.ensure_cluster("default")
        h2 = await mgr.ensure_cluster("default")
        assert h1 is h2
        # 仍只一条 default WS（无重连）
        assert len(ws_captures) == 1
        assert mgr.has_cluster("default")

    async def test_bootstrap_default_project_succeeds(
        self,
        engine_and_ws: tuple[SubjectEngine, dict[str, _FakeWS]],
    ) -> None:
        e, _ = engine_and_ws
        project_mgr = e.services.require(PROJECT_MANAGER)
        result = await project_mgr.handle_command("project_list", {})
        assert result["success"], result.get("error")
        assert result["data"]["count"] == 1
        assert result["data"]["projects"][0]["name"] == "default"

    async def test_multi_cluster_each_own_ws_init_cluster(
        self,
        engine_and_ws: tuple[SubjectEngine, dict[str, _FakeWS]],
    ) -> None:
        e, ws_captures = engine_and_ws
        mgr = e.services.require(CLUSTER_TRANSPORT_MANAGER)
        await mgr.ensure_cluster("c2")
        assert len(ws_captures) == 2
        assert "c2" in ws_captures
        c2_init = json.loads(ws_captures["c2"].sent[0])
        assert c2_init["type"] == "init_cluster"
        assert c2_init["payload"] == {"cluster_id": "c2"}
        # default 的 init_cluster 仍为 default，不受 c2 影响
        default_init = json.loads(ws_captures["default"].sent[0])
        assert default_init["payload"] == {"cluster_id": "default"}

    async def test_command_result_resolves_on_source_transport(
        self,
        engine_and_ws: tuple[SubjectEngine, dict[str, _FakeWS]],
    ) -> None:
        e, ws_captures = engine_and_ws
        mgr = e.services.require(CLUSTER_TRANSPORT_MANAGER)
        handle = mgr.get_handle("default")
        ws = ws_captures["default"]
        # 停止 auto-responder，手动注入特定回执以精确验证 source 关联 resolve
        await ws.stop_responder()

        spawn_task = asyncio.create_task(
            handle.spawn_agent(
                SpawnAgentPayload(config=AgentConfigPayload(name="a1"))
            )
        )
        await asyncio.sleep(0.05)
        sent = json.loads(ws.sent[-1])
        assert sent["type"] == "spawn_agent"
        request_id = sent["request_id"]
        await ws.incoming.put(
            json.dumps(
                {
                    "type": "command_result",
                    "payload": {
                        "success": True,
                        "data": {"name": "a1"},
                        "error": None,
                    },
                    "request_id": request_id,
                }
            )
        )
        result = await asyncio.wait_for(spawn_task, timeout=1.0)
        assert result["success"] is True
        assert result["data"] == {"name": "a1"}


class TestUnitRegistration:
    def test_full_profile_registers_cluster_transport_not_forward_or_core_unit(
        self,
    ) -> None:
        e = SubjectEngine(SubjectConfig())
        e.register_builtin_units(profile="full")
        assert e.get_unit("cluster_transport") is not None
        assert e.get_unit("websocket_core_transport") is None
        assert e.get_unit("forward") is None
