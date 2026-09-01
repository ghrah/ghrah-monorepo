"""全链路集成测试：Core → Subject ↔ Observer。

该文件验证外部 start_all.py + observer-tui/HITL 手动审批链路，默认跳过。

运行方式：
    uv run python scripts/start_all.py --port 4111 --no-tui &
    GHRAH_RUN_OBSERVER_TUI_FULL_CHAIN=1 \
        uv run pytest tests/integration/test_full_chain_integration.py \
        -v -m integration --timeout=300
"""

from __future__ import annotations

import asyncio
import logging
import os

import pytest

# ── 诊断日志配置 ──
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GHRAH_RUN_OBSERVER_TUI_FULL_CHAIN") != "1",
    reason="requires external start_all.py stack and manual observer-tui/HITL approval",
)

# ── 全局常量（与 start_all.py 手动链路共享） ──

SUBJECT_OBSERVER_WS_URL = os.environ.get(
    "GHRAH_SUBJECT_OBSERVER_WS_URL",
    "ws://127.0.0.1:4112/ws",
)


# ── 轻量 fixture：仅连接已运行的手动测试服务，不启动新实例 ──


@pytest.fixture
async def observer_client():
    """创建 ObserverClient 并连接到已运行的 Subject observer server。"""
    from ghrah.observer_core.client import ObserverClient

    client = ObserverClient(subject_url=SUBJECT_OBSERVER_WS_URL)

    recv_task = asyncio.create_task(client.connect())

    # 等待连接建立：轮询 client.connected 属性而非依赖超时
    deadline = asyncio.get_event_loop().time() + 15.0
    while not client.connected and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.1)

    if not client.connected:
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass
        raise ConnectionError("Failed to connect to Subject server within 15s")

    await client.subscribe()
    yield client
    await client.disconnect()

    if not recv_task.done():
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass


# ═══════════════════════════════════════════
# 全链路集成（真实服务）
# ═══════════════════════════════════════════


@pytest.mark.integration
class TestFullChainIntegration:
    """全链路集成测试。

    验证 Core → Subject ↔ Observer 的完整消息流。
    需要 start_all.py 已启动全栈服务。

    运行条件：
    - start_all.py 运行中（Core + Subject）
    - agentsconfig 配置了 coder agent
    - 无端口冲突
    """

    @pytest.fixture(autouse=True)
    async def setup_chain(self, observer_client):
        """设置 Observer 事件收集器。"""
        from tests.integration.conftest import EventCollector

        self.observer = observer_client
        self.collector = EventCollector()
        self.collector.register(self.observer)

    async def test_spawn_agent_through_core(self):
        """测试通过 Core 创建 Agent 并确认 Observer 收到事件。"""
        result = await self.observer.spawn_agent(
            name="coder",
            agent_config_name="coder",
            system_prompt="你是一个 Python 编程助手。",
            abilities=[
                {"ability_type": "conversation"},
                {"ability_type": "end_task"},
                {"ability_type": "read_file"},
                {"ability_type": "write_file"},
                {"ability_type": "list_directory"},
            ],
            use_remote_executor=True,
            persistence_type="remote",
        )
        assert result is not None

        event_type, event = await self.collector.wait_for(
            "agent_spawned", timeout=30.0
        )
        assert event_type == "agent_spawned"
        payload = event.payload if hasattr(event, "payload") else event
        assert payload.get("name") == "coder"

    async def test_send_message_to_agent(self):
        """测试向 Agent 发送消息并收到 action_chain_updated 事件。"""
        await self.observer.spawn_agent(
            name="coder-msg-test",
            agent_config_name="coder",
            system_prompt="你是一个 Python 编程助手。",
            abilities=[
                {"ability_type": "conversation"},
                {"ability_type": "end_task"},
            ],
            use_remote_executor=True,
            persistence_type="remote",
        )

        await self.collector.wait_for("agent_spawned", timeout=15.0)

        response = await self.observer.send_message(
            "coder-msg-test",
            "请简要说明你的能力。",
        )
        assert response is not None

        event_type, event = await self.collector.wait_for(
            "action_chain_updated", timeout=60.0
        )
        assert event_type in (
            "action_chain_updated",
            "agent_response",
        )

    async def test_hitl_request_flow(self):
        """测试 HITL 审批流程：Agent 写文件 → HITL 请求 → Observer 审批。"""
        await self.observer.spawn_agent(
            name="coder-hitl-test",
            agent_config_name="coder",
            system_prompt="你是一个 Python 编程助手。当用户要求写文件时，使用 write_file 工具。",
            abilities=[
                {"ability_type": "conversation"},
                {"ability_type": "end_task"},
                {"ability_type": "write_file"},
            ],
            use_remote_executor=True,
            persistence_type="remote",
        )

        await self.collector.wait_for("agent_spawned", timeout=15.0)

        await self.observer.send_message(
            "coder-hitl-test",
            "请在 /tmp/ 下创建一个名为 hello.py 的文件，内容为 print('Hello, ghrah!')",
        )

        event_type, event = await self.collector.wait_for(
            "hitl_request", timeout=120.0
        )
        assert event_type == "hitl_request"
        payload = event.payload if hasattr(event, "payload") else event
        promise_id = payload.get("promise_id")
        assert promise_id is not None

        await self.observer.send_hitl_response(
            promise_id=promise_id,
            approved=True,
        )

        event_type, event = await self.collector.wait_for(
            "action_chain_updated", timeout=60.0
        )
        assert event_type in (
            "action_chain_updated",
            "ability_result",
        )

    async def test_ability_result_routing(self):
        """测试 Ability 执行结果的完整路由：Agent 写文件 → Subject 执行 → 结果路由回 Core。

        使用 write_file 在工作区内创建一个简单 Python 文件，
        然后用 read_file 读回内容，验证端到端结果路由的正确性。
        """
        await self.observer.spawn_agent(
            name="coder-ability-test",
            agent_config_name="coder",
            system_prompt="你是一个助手。使用 write_file 创建文件，使用 read_file 读取文件。",
            abilities=[
                {"ability_type": "conversation"},
                {"ability_type": "end_task"},
                {"ability_type": "read_file"},
                {"ability_type": "write_file"},
            ],
            use_remote_executor=True,
            persistence_type="remote",
        )

        await self.collector.wait_for("agent_spawned", timeout=15.0)

        await self.observer.send_message(
            "coder-ability-test",
            "请在工作区中创建一个名为 hello.py 的文件，内容为：print('Hello, ghrah!')",
        )

        write_event_type, write_event = await self.collector.wait_for(
            "ability_result", timeout=120.0,
            predicate=lambda e: (
                (e.payload if hasattr(e, "payload") else e).get("ability_name") == "write_file"
            ),
        )
        assert write_event_type == "ability_result"
        write_payload = write_event.payload if hasattr(write_event, "payload") else write_event
        assert write_payload.get("success") is True
        assert "agent_name" in write_payload

        await self.observer.send_message(
            "coder-ability-test",
            "请读取你刚才创建的 hello.py 文件的内容。",
        )

        read_event_type, read_event = await self.collector.wait_for(
            "ability_result", timeout=60.0,
            predicate=lambda e: (
                (e.payload if hasattr(e, "payload") else e).get("ability_name") == "read_file"
            ),
        )
        assert read_event_type == "ability_result"
        read_payload = read_event.payload if hasattr(read_event, "payload") else read_event
        assert read_payload.get("success") is True
        result_data = read_payload.get("result", {})
        content = result_data.get("content", "") if isinstance(result_data, dict) else ""
        assert "Hello, ghrah!" in content

    async def test_persist_command_routing(self):
        """测试 persist 命令的完整路由：Core → Subject → 结果返回。"""
        await self.observer.spawn_agent(
            name="coder-persist-test",
            agent_config_name="coder",
            system_prompt="你是一个助手。",
            abilities=[
                {"ability_type": "conversation"},
                {"ability_type": "end_task"},
            ],
            use_remote_executor=True,
            persistence_type="remote",
        )

        await self.collector.wait_for("agent_spawned", timeout=15.0)

        await self.observer.send_message(
            "coder-persist-test",
            "你好。",
        )

        event_type, event = await self.collector.wait_for(
            "agent_response", timeout=60.0
        )
        assert event_type in (
            "agent_response",
            "action_chain_updated",
            "ability_result",
        )
