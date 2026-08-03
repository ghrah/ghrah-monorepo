from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from ghrah.subject.cluster_transport import ClusterHandle, ClusterTransportManager
from ghrah.subject.config import CoreTransportConfig
from ghrah.subject.transport.core import CoreMessage, InProcessCoreTransport


def _fake_factory(
    captures: dict[str, InProcessCoreTransport],
) -> Any:
    def make(config: CoreTransportConfig) -> InProcessCoreTransport:
        t = InProcessCoreTransport()
        captures[config.cluster_id] = t
        return t

    return make


def _cr(success: bool, data: Any = None, error: str | None = None) -> CoreMessage:
    """构造 command_result envelope payload（供 resolve_command_result）。"""
    return {
        "type": "command_result",
        "payload": {"success": success, "data": data, "error": error},
    }


@pytest.fixture
async def manager() -> AsyncIterator[
    tuple[ClusterTransportManager, dict[str, InProcessCoreTransport]]
]:
    captures: dict[str, InProcessCoreTransport] = {}
    m = ClusterTransportManager(
        CoreTransportConfig(),
        on_message=lambda msg, *, source: asyncio.sleep(0),
        transport_factory=_fake_factory(captures),
    )
    try:
        yield m, captures
    finally:
        await m.stop()


class TestClusterTransportManager:
    async def test_ensure_cluster_creates_handle(
        self, manager: tuple[ClusterTransportManager, dict[str, InProcessCoreTransport]]
    ) -> None:
        m, captures = manager
        handle = await m.ensure_cluster("c1")
        assert isinstance(handle, ClusterHandle)
        assert handle.cluster_id == "c1"
        assert m.has_cluster("c1")
        assert "c1" in captures
        assert captures["c1"].is_connected

    async def test_ensure_cluster_idempotent(
        self, manager: tuple[ClusterTransportManager, dict[str, InProcessCoreTransport]]
    ) -> None:
        m, captures = manager
        h1 = await m.ensure_cluster("c1")
        h2 = await m.ensure_cluster("c1")
        assert h1 is h2
        assert len(captures) == 1  # 只建一个 transport

    async def test_get_handle_missing_raises_keyerror(
        self, manager: tuple[ClusterTransportManager, dict[str, InProcessCoreTransport]]
    ) -> None:
        m, _ = manager
        with pytest.raises(KeyError):
            m.get_handle("nope")

    async def test_shutdown_cluster_removes_handle(
        self, manager: tuple[ClusterTransportManager, dict[str, InProcessCoreTransport]]
    ) -> None:
        m, captures = manager
        await m.ensure_cluster("c1")
        await m.shutdown_cluster("c1")
        assert not m.has_cluster("c1")
        assert not captures["c1"].is_connected

    async def test_shutdown_missing_cluster_noop(
        self, manager: tuple[ClusterTransportManager, dict[str, InProcessCoreTransport]]
    ) -> None:
        m, _ = manager
        await m.shutdown_cluster("nope")  # 不报错

    async def test_stop_closes_all(
        self, manager: tuple[ClusterTransportManager, dict[str, InProcessCoreTransport]]
    ) -> None:
        m, captures = manager
        await m.ensure_cluster("c1")
        await m.ensure_cluster("c2")
        await m.stop()
        assert not captures["c1"].is_connected
        assert not captures["c2"].is_connected
        assert m.cluster_ids == []

    async def test_requires_on_message(self) -> None:
        m = ClusterTransportManager(
            CoreTransportConfig(),
            transport_factory=_fake_factory({}),
        )
        with pytest.raises(RuntimeError, match="on_message"):
            await m.ensure_cluster("c1")


class TestClusterHandle:
    async def _make_handle(
        self, captures: dict[str, InProcessCoreTransport]
    ) -> tuple[ClusterHandle, InProcessCoreTransport]:
        m = ClusterTransportManager(
            CoreTransportConfig(),
            on_message=lambda msg, *, source: asyncio.sleep(0),
            transport_factory=_fake_factory(captures),
        )
        handle = await m.ensure_cluster("c1")
        transport = captures["c1"]
        return handle, transport

    async def test_spawn_agent_sends_and_parses_command_result(self) -> None:
        captures: dict[str, InProcessCoreTransport] = {}
        handle, transport = await self._make_handle(captures)
        # 准备：spawn_agent send_and_wait 会注册 pending，模拟 Core 回 command_result
        from ghrah.protocol.types import AgentConfigPayload, SpawnAgentPayload

        async def respond() -> None:
            await asyncio.sleep(0.01)
            sent = transport.sent_messages[-1]
            transport.resolve_command_result(
                sent["request_id"], _cr(True, {"name": "a1"})
            )

        asyncio.create_task(respond())
        result = await handle.spawn_agent(
            SpawnAgentPayload(config=AgentConfigPayload(name="a1"))
        )
        assert result["success"] is True
        assert result["data"] == {"name": "a1"}
        assert transport.sent_messages[-1]["type"] == "spawn_agent"

    async def test_list_agents_returns_list(self) -> None:
        captures: dict[str, InProcessCoreTransport] = {}
        handle, transport = await self._make_handle(captures)

        async def respond() -> None:
            await asyncio.sleep(0.01)
            sent = transport.sent_messages[-1]
            transport.resolve_command_result(
                sent["request_id"], _cr(True, [{"name": "a1"}])
            )

        asyncio.create_task(respond())
        agents = await handle.list_agents()
        assert agents == [{"name": "a1"}]

    async def test_list_agents_failure_returns_empty(self) -> None:
        captures: dict[str, InProcessCoreTransport] = {}
        handle, transport = await self._make_handle(captures)

        async def respond() -> None:
            await asyncio.sleep(0.01)
            sent = transport.sent_messages[-1]
            transport.resolve_command_result(
                sent["request_id"], _cr(False, error="x")
            )

        asyncio.create_task(respond())
        agents = await handle.list_agents()
        assert agents == []

    async def test_terminate_agent(self) -> None:
        captures: dict[str, InProcessCoreTransport] = {}
        handle, transport = await self._make_handle(captures)

        async def respond() -> None:
            await asyncio.sleep(0.01)
            sent = transport.sent_messages[-1]
            transport.resolve_command_result(
                sent["request_id"], _cr(True)
            )

        asyncio.create_task(respond())
        result = await handle.terminate_agent("a1")
        assert result["success"] is True
        assert transport.sent_messages[-1]["type"] == "terminate_agent"

    async def test_shutdown_fire_and_forget(self) -> None:
        captures: dict[str, InProcessCoreTransport] = {}
        handle, transport = await self._make_handle(captures)
        await handle.shutdown()
        assert transport.sent_messages[-1]["type"] == "shutdown_cluster"

    async def test_parse_invalid_command_result(self) -> None:
        captures: dict[str, InProcessCoreTransport] = {}
        handle, transport = await self._make_handle(captures)

        async def respond() -> None:
            await asyncio.sleep(0.01)
            sent = transport.sent_messages[-1]
            transport.resolve_command_result(
                sent["request_id"], {"type": "command_result", "payload": "not-a-dict"}
            )

        asyncio.create_task(respond())
        result = await handle.list_agents()
        assert result == []
        _ = handle  # 占位避免未用
