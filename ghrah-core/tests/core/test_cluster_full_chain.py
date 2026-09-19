# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""集群能力全链路测试（mock LLM 驱动真实 agent loop）。

父 agent 的 ScriptedLLM 按脚本返回 tool_calls（query_agents →
spawn_agent → send_message）驱动真实集群能力回路，最终以纯文本收束；
子 agent（经 spawn_agent ability 以 manifest 冻结能力面创建）以独立
ScriptedLLM 应答。断言全部落在真实副作用上：

1. query_agents 返回集群成员事实（工具结果进入链上下文）；
2. spawn_agent ability（auto_approve 白名单放行，HITL 结构性门仍在
   ——审批路径的完整往返由 test_c2_integration 覆盖）→
   ManifestResolver 解析 → supervisor.spawn_agent（集群级 llm_factory
   默认继承——子 agent 同走注入 LLM，不回落 agentconf）；
3. send_message（同步模式）→ 子 agent receive → 子 ScriptedLLM 推理
   → 回复送达父 agent 的 receive 返回值；
4. 父 agent 最终回复 = 文本收束（全链路跑完的证明）。

无 unittest.mock；全链路为 CoreUnit + SupervisorActor + AgentBuilder
真实组件，仅 LLM 为脚本化假实现。
"""

from __future__ import annotations

from typing import Any

from _helpers import ScriptedLLM
from test_core_unit import FakeCtx

from ghrah.chat.content import ToolCallBlock
from ghrah.core.message import AgentMessage, MessageType
from ghrah.core.unit import CoreUnitConfig, create_core_unit
from ghrah.manifest.parser import parse_agent_manifest
from ghrah.manifest.protocols import ManifestStoreProtocol
from ghrah.manifest.store import BuiltinManifestStore

_ORCHESTRATOR_YAML = """\
manifest: agent
version: "1"
metadata:
  namespace: cluster
  name: orchestrator
  description: orchestrator
model:
  agent_config_name: default
system_prompt: You orchestrate.
max_iterations: 8
abilities:
  - type: conversation
  - type: end_task
  - ref: ghrah.cluster.query_agents
  - ref: ghrah.cluster.spawn_agent
  - ref: ghrah.cluster.send_message
"""

_WORKER_YAML = """\
manifest: agent
version: "1"
metadata:
  namespace: cluster
  name: worker
  description: worker
model:
  agent_config_name: default
system_prompt: You work.
max_iterations: 5
abilities:
  - type: conversation
  - type: end_task
"""


class _CompositeStore(ManifestStoreProtocol):
    """builtin cluster 工具 manifests + 两个 agent manifests。"""

    def __init__(self) -> None:
        self._builtin = BuiltinManifestStore()
        self._agents = {
            "cluster.orchestrator": parse_agent_manifest(_ORCHESTRATOR_YAML),
            "cluster.worker": parse_agent_manifest(_WORKER_YAML),
        }

    def load_ability(self, full_name: str) -> Any:
        return self._builtin.load_ability(full_name)

    def load_agent(self, full_name: str) -> Any:
        return self._agents[full_name]

    def list_abilities(self, namespace: str | None = None) -> list[str]:
        return self._builtin.list_abilities(namespace)

    def list_agents(self, namespace: str | None = None) -> list[str]:
        return list(self._agents)


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> ToolCallBlock:
    return ToolCallBlock(id=call_id, name=name, arguments=arguments)


async def test_cluster_abilities_full_chain_with_scripted_tool_calls() -> None:
    """query_agents → spawn_agent → send_message 全链路（真实能力回路）。"""
    # 父 LLM：三轮 tool_call + 文本收束；子 LLM 预设回复
    parent_llm = _ToolScriptedLLM(
        rounds=[
            [
                _tool_call("call-1", "query_agents", {}),
            ],
            [
                _tool_call(
                    "call-2",
                    "spawn_agent",
                    {"manifest_ref": "cluster.worker", "name": "worker-1"},
                )
            ],
            [
                _tool_call(
                    "call-3",
                    "send_message",
                    {
                        "target": "worker-1",
                        "content": "请报告状态",
                        "fire_and_forget": False,
                    },
                )
            ],
        ],
        final_text="编排完成：worker 已应答",
    )
    worker_llm = ScriptedLLM(replies=["worker 就绪，任务已领"])

    # 集群级 llm_factory：按 AgentConfig 路由（子 agent 继承同一工厂）
    def llm_factory(config: Any) -> Any:
        if config.name == "orchestrator":
            return parent_llm
        if config.name == "worker-1":
            return worker_llm
        raise AssertionError(f"unexpected agent spawned: {config.name}")

    unit = create_core_unit(
        CoreUnitConfig(
            project_id="default",
            cluster_id="cluster-e2e",
            manifest_store=_CompositeStore(),
            llm_factory=llm_factory,
            # 部署管理员放行 spawn_agent（manifest require_hitl: true 的
            # 显式覆盖层；HITL 审批往返由 test_c2_integration 覆盖）
            auto_approve_abilities=("spawn_agent",),
        )
    )
    ctx = FakeCtx()
    await unit.init(ctx)

    # 父 agent 经 manifest_ref spawn（能力面含集群三工具）
    spawn = await unit.handle_command(
        "spawn_agent",
        {
            "project_id": "default",
            "config": {"name": "orchestrator"},
            "manifest_ref": "cluster.orchestrator",
        },
        None,
    )
    assert spawn["success"], spawn.get("error")

    orchestrator = await unit.supervisor.get_agent_handle("orchestrator")
    reply = await orchestrator.receive(
        AgentMessage(
            sender="user",
            recipient="orchestrator",
            content="启动编排",
            type=MessageType.CHAT,
        )
    )

    # 4. 最终回复 = 父 agent 文本收束（全链路跑完的证明）
    assert reply.type == MessageType.RESULT
    assert reply.content == "编排完成：worker 已应答"

    # 副作用断言：worker-1 已注册进集群（spawn_agent ability 路径）
    listed = await unit.supervisor.list_agents()
    names = [a["name"] for a in listed]
    assert "orchestrator" in names
    assert "worker-1" in names

    # 子 agent 确实消费了注入的 LLM（集群级默认继承，非 agentconf 回落）
    assert len(worker_llm.calls) == 1

    # 工具回路证据：send_message 的同步回复（worker 预设文本）作为消息
    # 进入父 agent 历史（router 回注路径的真实副作用）
    worker_handle = await unit.supervisor.get_agent_handle("worker-1")
    assert worker_handle._message_history, "worker should have received the message"
    received = worker_handle._message_history[0]
    assert received.content == "请报告状态"
    assert received.sender == "orchestrator"

    # 同步回复文本进入父 agent 上下文：收束轮的 LLM 输入含 worker 预设回复
    final_call = parent_llm.calls[-1]
    assert any("worker 就绪，任务已领" in str(m) for m in final_call)


class _ToolScriptedLLM(ScriptedLLM):
    """按轮次返回 tool_call 块（末轮返回纯文本收束）。"""

    def __init__(self, rounds: list[list[ToolCallBlock]], final_text: str) -> None:
        super().__init__(replies=[])
        self._rounds = list(rounds)
        self._final_text = final_text
        self._turn = 0

    async def generate(self, messages: list[Any], tools: list[dict[str, Any]] | None = None) -> Any:
        from ghrah.chat.content import TextBlock
        from ghrah.chat.format import LLMResponse

        self.calls.append(list(messages))
        if self._turn < len(self._rounds):
            blocks: list[Any] = list(self._rounds[self._turn])
            self._turn += 1
            return LLMResponse(content_blocks=blocks)
        return LLMResponse(content_blocks=[TextBlock(text=self._final_text)])
