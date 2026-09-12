# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""Agent 域载荷模型。

Agent 生命周期/能力/订阅/HITL/集群命令与事件、上下文占用与 compact 命令载荷。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ─── 命令载荷模型 ───


class AgentConfigPayload(BaseModel):
    """Agent 配置载荷，对应 ghrah-core 的 AgentConfig。"""

    name: str
    agent_id: str = ""
    agent_config_name: str | None = None
    description: str = ""
    system_prompt: str = ""
    max_iterations: int = 10
    communication_timeout: float = 300.0
    window: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    model_overrides: dict[str, Any] | None = None


class SpawnAgentPayload(BaseModel):
    """spawn_agent 命令载荷。"""

    project_id: str
    cluster_id: str = ""
    config: AgentConfigPayload
    abilities: list[AbilityDefinitionPayload] | None = None
    manifest_ref: str | None = None


class TerminateAgentPayload(BaseModel):
    """terminate_agent 命令载荷。"""

    project_id: str
    agent_id: str
    name: str


class SendMessagePayload(BaseModel):
    """send_message 命令载荷。"""

    project_id: str
    agent_id: str
    target: str
    content: str
    sender: str = "user"
    timeout: float | None = None
    metadata: dict[str, Any] | None = None
    """扩展元数据（透传至 AgentMessage.metadata；如 Room 投递写入 room_id）。

    回复归属推导经链节点 messages_delta（receive 侧将 metadata 合入用户
    ChatMessage），非回复消息回传。
    """


class BroadcastMessagePayload(BaseModel):
    """broadcast_message 命令载荷。"""

    project_id: str
    content: str
    sender: str = "user"


class AbilityDefinitionPayload(BaseModel):
    """Ability 定义载荷。

    用于从 Subject 传输 Ability 配置到 Core。
    ability_type 映射到 ghrah-core 中内置的 Ability 类。
    """

    ability_type: str
    params: dict[str, Any] = Field(default_factory=dict)


class RegisterAbilityPayload(BaseModel):
    """register_ability 命令载荷。"""

    project_id: str
    agent_id: str
    agent_name: str
    ability: AbilityDefinitionPayload


class ListAgentsPayload(BaseModel):
    """list_agents 命令载荷（Project-scoped）。"""

    project_id: str


class HealthCheckPayload(BaseModel):
    """health_check 命令载荷（空载荷）。"""

    pass


class DelegatePayload(BaseModel):
    """delegate 命令载荷。"""

    project_id: str
    from_agent_id: str
    to_agent_id: str
    from_agent: str
    to_agent: str
    content: str
    timeout: float | None = None


class SubscribePayload(BaseModel):
    """subscribe 命令载荷。"""

    agent_names: list[str] | None = None  # None 表示订阅全部
    event_types: list[str] | None = None  # None 表示订阅全部事件类型


class UnsubscribePayload(BaseModel):
    """unsubscribe 命令载荷。"""

    agent_names: list[str] | None = None
    event_types: list[str] | None = None


class ExecuteAbilityPayload(BaseModel):
    """execute_ability 命令载荷。

    Core → Subject：请求 Subject 执行 Ability。
    """

    request_id: str
    agent_name: str
    ability_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)  # ─── 事件载荷模型 ───


class AgentSpawnedPayload(BaseModel):
    """agent_spawned 事件载荷。"""

    project_id: str = ""
    cluster_id: str = ""
    name: str
    agent_id: str = ""
    incarnation_id: str = ""
    recovery_mode: str = ""
    config: AgentConfigPayload


class AgentTerminatedPayload(BaseModel):
    """agent_terminated 事件载荷。"""

    project_id: str = ""
    cluster_id: str = ""
    name: str
    agent_id: str = ""
    incarnation_id: str = ""


class AgentResponsePayload(BaseModel):
    """agent_response 事件载荷。"""

    project_id: str = ""
    agent_id: str = ""
    cluster_id: str = ""
    sender: str
    recipient: str
    content: str
    content_blocks: list[dict[str, Any]] | None = None
    message_type: str = "result"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionChainUpdatedPayload(BaseModel):
    """action_chain_updated 事件载荷。"""

    project_id: str = ""
    agent_id: str = ""
    cluster_id: str = ""
    agent_name: str
    node: dict[str, Any] = Field(default_factory=dict)


class AgentErrorPayload(BaseModel):
    """agent_error 事件载荷。"""

    project_id: str = ""
    agent_id: str = ""
    cluster_id: str = ""
    agent_name: str
    error: str


class HealthStatusPayload(BaseModel):
    """health_status 事件载荷。"""

    status: dict[str, bool]


class AbilityResultPayload(BaseModel):
    """ability_result 事件载荷。

    Core → Subject → Observer：Core 已确认收到的 Ability 执行结果事件。
    执行结果来源于 Subject 返回的 execute_ability command_result。
    """

    project_id: str = ""
    agent_id: str = ""
    cluster_id: str = ""
    request_id: str
    agent_name: str
    ability_name: str
    success: bool
    result: Any = None
    error: str | None = None


class HITLRequestPayload(BaseModel):
    """hitl_request 事件载荷。

    Subject → Observer：HITL 审批请求。
    当 AbilityRunner 判断某操作需要人工审批时，创建 Promise 并广播此事件。
    """

    project_id: str = ""
    agent_id: str = ""
    cluster_id: str = ""
    promise_id: str
    agent_name: str
    ability_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class ContextUsageUpdatedPayload(BaseModel):
    """context_usage_updated 事件载荷。

    Core → Subject → Observer：上下文占用状态感知出口（pre_call/post_call
    双相位）。occupied_tokens 为真实 usage 权威口径：pre_call 取占用锚点
    （可能为 None，如首次调用/head 变更后），post_call 取本次 LLM 调用
    真实 input_tokens（basis="real"，归一化口径：恒为总输入，含缓存
    部分）。budget_tokens 为落定预算（无 WindowManager 时为 0），来源由
    budget_source 标注：显式声明（declared）/ 模型窗口表（model_table）/
    内置默认（default）/ 厂商超限错误回填（vendor）。
    """

    project_id: str = ""
    agent_id: str = ""
    cluster_id: str = ""
    agent_name: str
    phase: str
    """发布相位："pre_call"（发送前，占用锚点口径）/ "post_call"（响应后，真实值口径）"""
    occupied_tokens: int | None = None
    basis: str
    """occupied_tokens 计量口径："anchor"（占用锚点）/"real"（本次调用真实值）"""
    budget_tokens: int = 0
    budget_source: str | None = None
    """预算来源："declared"/"model_table"/"default"/"vendor"（无 WindowManager 时为 None）"""
    compact_threshold: float | None = None
    real_input_tokens: int | None = None
    """本次调用总输入 token 数（归一化口径，含缓存命中与缓存写入部分）"""
    real_output_tokens: int | None = None
    real_cache_read_tokens: int | None = None
    """本次调用缓存命中读 token 数（pre_call 或厂商未上报时为 None/0）"""
    real_cache_write_tokens: int | None = None
    """本次调用缓存写入 token 数（pre_call 或厂商未上报时为 None/0）"""
    compaction: dict[str, Any] | None = None
    """本轮压缩决策记录（compaction_decision；未配置窗口时为 None）"""
    iteration: int | None = None


class HITLResponsePayload(BaseModel):
    """hitl_response 命令载荷。

    Observer → Subject（分布式）/ Observer → Core（单体）：HITL 审批响应。

    存在两条数据流，字段集合不同，故全部字段（除 approved）设默认值以兼容：
    - 分布式（Subject 侧）：promise_id / approved / reason
      （SubjectService._handle_hitl_response 据此 resolve Promise）
    - 单体（Core 侧）：agent_name / ability_name / tool_call_id / approved / result
      （core/router._handle_hitl_response 据此 resolve HITLFutureStore）
    """

    # 分布式路径字段
    promise_id: str = ""
    # 单体路径字段
    agent_name: str = ""
    ability_name: str = ""
    tool_call_id: str = ""
    # 两路径共有
    approved: bool
    # 分布式：拒绝原因；单体：审批附加结果
    reason: str | None = None
    result: Any = None


class UnregisterAbilityPayload(BaseModel):
    """unregister_ability 命令载荷。"""

    project_id: str
    agent_id: str
    agent_name: str
    ability_name: str


class GetAgentInfoPayload(BaseModel):
    """get_agent_info 命令载荷。"""

    project_id: str
    agent_id: str
    name: str


class AgentCompactContextPayload(BaseModel):
    """agent_compact_context 命令载荷。

    Observer → Subject → Core：手动触发链上 compact 回合。
    迭代中：置标志、下一节点提交前消费、进 compact 回合；空闲：直接执行
    一轮 compact；连续多次请求合并（幂等）。
    """

    project_id: str
    agent_id: str
    agent_name: str
    cluster_id: str = ""


class InitClusterPayload(BaseModel):
    """init_cluster 命令载荷。"""

    cluster_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class ShutdownClusterPayload(BaseModel):
    """shutdown_cluster 命令载荷。"""

    cluster_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class ClusterStatusPayload(BaseModel):
    """cluster_status 命令载荷。"""

    cluster_id: str


class ListClustersPayload(BaseModel):
    """list_clusters 命令载荷（空载荷）。"""

    pass


class ClusterInfoPayload(BaseModel):
    """单个集群的信息（list_clusters 结果项）。"""

    cluster_id: str
    active_agents: int
    status: str
    bound: bool


class ListClustersResultPayload(BaseModel):
    """list_clusters 命令结果载荷。"""

    clusters: list[ClusterInfoPayload]
