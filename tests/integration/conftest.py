"""全链路集成测试 fixtures。

提供程序化启动 Core → Subject → Observer 的夹具，
以及事件收集工具 EventCollector。

使用方式：test_full_chain_integration.py 中 @pytest.mark.integration 测试。
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

logger = logging.getLogger(__name__)

# ── 全局常量 ──


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


CORE_PORT = int(os.environ.get("GHRAH_TEST_CORE_PORT") or _free_tcp_port())
CORE_WS_URL = f"ws://127.0.0.1:{CORE_PORT}/ws"
SUBJECT_PORT = int(os.environ.get("GHRAH_TEST_SUBJECT_PORT") or _free_tcp_port())
SUBJECT_OBSERVER_WS_URL = f"ws://127.0.0.1:{SUBJECT_PORT}/ws"
HITL_TIMEOUT = 120
ABILITY_TIMEOUT = 60
TEST_WORKSPACE_ROOT = tempfile.mkdtemp(prefix="ghrah-test-workspace-")
TEST_DB_PATH = os.path.join(tempfile.mkdtemp(prefix="ghrah-test-"), "subject.db")


# ── Fixtures ──


@pytest.fixture(scope="module")
def event_loop():
    """创建模块级事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def core_server():
    """启动 Core FastAPI 服务器（内含 SupervisorActor）。"""
    import uvicorn
    from ghrah.core.server.app import create_app
    from ghrah.core.server.config import CoreServerConfig

    config = CoreServerConfig(
        port=CORE_PORT,
        log_level="WARNING",
    )
    app = create_app(config)
    server_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=CORE_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(server_config)

    task = asyncio.create_task(server.serve())
    # 等待服务器启动
    await asyncio.sleep(2.0)
    yield server
    # 关闭服务器
    server.should_exit = True
    await asyncio.sleep(1.0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.fixture(scope="module")
async def subject_server(core_server):
    """启动 Subject Observer FastAPI 服务器（SubjectEngine 装配，profile=full）。"""
    import uvicorn
    from ghrah.subject.config import (
        CoreConnectionConfig,
        HITLPolicyConfig,
        SubjectConfig,
    )
    from ghrah.subject.runtime.engine import SubjectEngine
    from ghrah.subject.server.app import create_app as create_subject_app
    from ghrah.subject.server.config import ObserverServerConfig

    subject_config = SubjectConfig(
        workspace_root=TEST_WORKSPACE_ROOT,
        db_path=TEST_DB_PATH,
        hitl_policy=HITLPolicyConfig(
            auto_approve_abilities=[
                "conversation",
                "end_task",
                "read_file",
                "list_directory",
                "write_file",
            ],
            require_approval_by_default=True,
        ),
        core=CoreConnectionConfig(
            url=CORE_WS_URL,
            command_timeout=ABILITY_TIMEOUT,
        ),
    )

    engine = SubjectEngine(subject_config)
    engine.register_builtin_units(profile="full")
    engine.discover()
    engine.enable_from_config()
    engine.validate()
    await engine.start()

    observer_config = ObserverServerConfig(
        port=SUBJECT_PORT,
        log_level="WARNING",
    )
    subject_app = create_subject_app(observer_config, engine=engine)
    server_config = uvicorn.Config(
        subject_app,
        host="127.0.0.1",
        port=SUBJECT_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(server_config)

    task = asyncio.create_task(server.serve())
    await asyncio.sleep(2.0)
    yield server
    server.should_exit = True
    await asyncio.sleep(1.0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await engine.stop()


@pytest.fixture
def subject_observer_ws_url() -> str:
    """返回本轮 integration fixture 启动的 Subject observer WebSocket URL。"""
    return SUBJECT_OBSERVER_WS_URL


@pytest.fixture
async def observer_client(subject_server):
    """创建并连接 ObserverClient 到 Subject observer server。"""
    from ghrah.observer_core.client import ObserverClient

    client = ObserverClient(subject_url=SUBJECT_OBSERVER_WS_URL)

    recv_task = asyncio.create_task(client.connect())

    # 等待连接建立
    deadline = time.monotonic() + 15.0
    while not client.connected and time.monotonic() < deadline:
        await asyncio.sleep(0.1)

    if not client.connected:
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass
        raise ConnectionError("Failed to connect to Subject server within 15s")

    # 订阅所有事件
    await client.subscribe()
    yield client
    await client.disconnect()

    if not recv_task.done():
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass


# ── Helper: 收集事件的队列 ──


@dataclass
class EventCollector:
    """收集 Observer 接收到的事件，按类型分类。"""

    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    _handlers: dict[str, list[Any]] = field(default_factory=dict)
    _cancelled: bool = False

    def register(self, client: Any) -> None:
        """注册 ObserverClient 的事件处理器。"""
        from ghrah.observer_core import EventType

        for et in EventType:
            handler = self._make_handler(et.value)
            client.on(et.value, handler)
            self._handlers.setdefault(et.value, []).append(handler)

    def _make_handler(self, event_type: str):
        """为指定事件类型创建处理器。"""

        async def handler(message: Any) -> None:
            await self.events.put((event_type, message))

        return handler

    async def wait_for(
        self,
        event_type: str,
        timeout: float = 30.0,
        predicate: Any = None,
    ) -> tuple[str, Any]:
        """等待指定类型的事件。"""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for event_type={event_type}")
            try:
                et, msg = await asyncio.wait_for(self.events.get(), timeout=remaining)
            except TimeoutError:
                raise TimeoutError(f"Timed out waiting for event_type={event_type}")

            if et == event_type:
                if predicate is None or predicate(msg):
                    return (et, msg)

    async def collect_until(
        self,
        event_type: str,
        timeout: float = 30.0,
        max_count: int = 10,
    ) -> list[tuple[str, Any]]:
        """收集指定类型的事件直到超时或达到上限。"""
        results: list[tuple[str, Any]] = []
        deadline = time.monotonic() + timeout
        while len(results) < max_count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                et, msg = await asyncio.wait_for(self.events.get(), timeout=max(0.1, remaining))
                if et == event_type:
                    results.append((et, msg))
            except TimeoutError:
                break
        return results
