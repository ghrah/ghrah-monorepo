# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""共享协议类型定义。

定义所有 WebSocket 消息的信封格式和载荷模型。
使用 Pydantic 确保类型安全和 JSON 序列化兼容性。
"""

from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ─── 客户端类型枚举 ───


class ClientType(StrEnum):
    """WebSocket 连接的客户端类型。

    区分 Subject 连接、Observer 连接和 Core 连接，
    用于事件广播时按类型过滤目标。

    - SUBJECT: Subject 服务连接，执行 Ability、持久化等
    - OBSERVER: Observer 客户端连接，接收事件、下发命令
    - CORE: Agent 的 CoreClient 连接，发布事件、请求执行 Ability
    """

    SUBJECT = "subject"
    OBSERVER = "observer"
    CORE = "core"


# ─── 消息类型枚举 ───


class CommandType(StrEnum):
    """命令类型。

    Observer → Subject → Core:
        Agent 管理命令，Observer 发起，经 Subject 转发到 Core。

    Observer → Subject:
        Workspace 管理命令，Observer 发起，Subject 本地处理。

    Core → Subject:
        Ability 执行和持久化命令，Core 发起，Subject 处理。

    Observer → Subject:
        HITL 响应命令，Observer 发起，Subject 处理。

    Observer (local):
        订阅命令，本地处理。
    """

    # ─── Agent 管理类（Observer → Subject → Core）───
    SPAWN_AGENT = "spawn_agent"
    TERMINATE_AGENT = "terminate_agent"
    SEND_MESSAGE = "send_message"
    BROADCAST_MESSAGE = "broadcast_message"
    REGISTER_ABILITY = "register_ability"
    UNREGISTER_ABILITY = "unregister_ability"
    LIST_AGENTS = "list_agents"
    HEALTH_CHECK = "health_check"
    DELEGATE = "delegate"
    GET_AGENT_INFO = "get_agent_info"

    # ─── Supervisor 类（Observer → Subject → Core）───
    INIT_CLUSTER = "init_cluster"
    SHUTDOWN_CLUSTER = "shutdown_cluster"
    CLUSTER_STATUS = "cluster_status"

    # ─── 订阅类（Observer 本地处理）───
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"

    # ─── Ability 执行类（Core → Subject）───
    EXECUTE_ABILITY = "execute_ability"

    # ─── HITL 类（Observer → Subject）───
    HITL_RESPONSE = "hitl_response"

    # ─── 持久化类（Core → Subject）───
    PERSIST_SAVE_NODE = "persist_save_node"
    PERSIST_LOAD_NODE = "persist_load_node"
    PERSIST_LOAD_CHAIN = "persist_load_chain"
    PERSIST_SAVE_CHAIN_META = "persist_save_chain_meta"
    PERSIST_LOAD_CHAIN_META = "persist_load_chain_meta"
    PERSIST_SAVE_MESSAGES = "persist_save_messages"
    PERSIST_LOAD_MESSAGES = "persist_load_messages"
    PERSIST_DELETE_CHAIN = "persist_delete_chain"
    PERSIST_LIST_AGENTS = "persist_list_agents"
    PERSIST_SAVE_SESSION = "persist_save_session"
    PERSIST_LOAD_SESSION = "persist_load_session"
    PERSIST_LIST_SESSIONS = "persist_list_sessions"
    PERSIST_DELETE_SESSIONS = "persist_delete_sessions"

    # ─── Workspace 管理类（Observer → Subject）───
    CREATE_WORKSPACE = "create_workspace"
    DESTROY_WORKSPACE = "destroy_workspace"
    WORKSPACE_SNAPSHOT = "workspace_snapshot"
    WORKSPACE_ROLLBACK = "workspace_rollback"
    WORKSPACE_DIFF = "workspace_diff"
    WORKSPACE_STATUS = "workspace_status"

    # ─── Session 管理类（Observer → Subject → Core）───
    SESSION_CREATE = "session_create"
    SESSION_SWITCH = "session_switch"
    SESSION_LIST = "session_list"
    SESSION_ARCHIVE = "session_archive"
    SESSION_DELETE = "session_delete"

    # ─── Manifest CRUD 类（Observer → Subject）───
    MANIFEST_LIST_ABILITIES = "manifest_list_abilities"
    MANIFEST_GET_ABILITY = "manifest_get_ability"
    MANIFEST_PUT_ABILITY = "manifest_put_ability"
    MANIFEST_DELETE_ABILITY = "manifest_delete_ability"
    MANIFEST_LIST_AGENTS = "manifest_list_agents"
    MANIFEST_GET_AGENT = "manifest_get_agent"
    MANIFEST_PUT_AGENT = "manifest_put_agent"
    MANIFEST_DELETE_AGENT = "manifest_delete_agent"
    MANIFEST_RESOLVE_AGENT = "manifest_resolve_agent"
    MANIFEST_VALIDATE = "manifest_validate"

    # ─── Chain History 类（Observer → Subject）───
    GET_CHAIN_HISTORY = "get_chain_history"


class EventType(StrEnum):
    """事件类型。

    方向说明：
    - Core 事件：Core → Subject + Observer
    - Subject 事件：Subject → Core + Observer
    - HITL 事件：Subject → Observer
    """

    AGENT_SPAWNED = "agent_spawned"
    AGENT_TERMINATED = "agent_terminated"
    AGENT_RESPONSE = "agent_response"
    ACTION_CHAIN_UPDATED = "action_chain_updated"
    AGENT_ERROR = "agent_error"
    HEALTH_STATUS = "health_status"
    ABILITY_RESULT = "ability_result"
    HITL_REQUEST = "hitl_request"
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_DESTROYED = "workspace_destroyed"
    WORKSPACE_SNAPSHOT_CREATED = "workspace_snapshot_created"
    WORKSPACE_ROLLED_BACK = "workspace_rolled_back"

    # ─── Manifest 变更事件（Subject → Observer）───
    MANIFEST_ABILITY_CREATED = "manifest_ability_created"
    MANIFEST_ABILITY_UPDATED = "manifest_ability_updated"
    MANIFEST_ABILITY_DELETED = "manifest_ability_deleted"
    MANIFEST_AGENT_CREATED = "manifest_agent_created"
    MANIFEST_AGENT_UPDATED = "manifest_agent_updated"
    MANIFEST_AGENT_DELETED = "manifest_agent_deleted"

    # ─── Session 事件（Core → Observer）───
    SESSION_CREATED = "session_created"
    SESSION_SWITCHED = "session_switched"
    SESSION_ARCHIVED = "session_archived"
    SESSION_DELETED = "session_deleted"
    SESSION_LIST_RESULT = "session_list_result"


class SystemType(StrEnum):
    """系统消息类型。"""

    COMMAND_RESULT = "command_result"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


MessageType = CommandType | EventType | SystemType

PERSIST_COMMANDS: frozenset[str] = frozenset({
    CommandType.PERSIST_SAVE_NODE.value,
    CommandType.PERSIST_LOAD_NODE.value,
    CommandType.PERSIST_LOAD_CHAIN.value,
    CommandType.PERSIST_SAVE_CHAIN_META.value,
    CommandType.PERSIST_LOAD_CHAIN_META.value,
    CommandType.PERSIST_SAVE_MESSAGES.value,
    CommandType.PERSIST_LOAD_MESSAGES.value,
    CommandType.PERSIST_DELETE_CHAIN.value,
    CommandType.PERSIST_LIST_AGENTS.value,
    CommandType.PERSIST_SAVE_SESSION.value,
    CommandType.PERSIST_LOAD_SESSION.value,
    CommandType.PERSIST_LIST_SESSIONS.value,
    CommandType.PERSIST_DELETE_SESSIONS.value,
})

CORE_COMMANDS: frozenset[str] = frozenset({
    CommandType.SPAWN_AGENT.value,
    CommandType.TERMINATE_AGENT.value,
    CommandType.SEND_MESSAGE.value,
    CommandType.BROADCAST_MESSAGE.value,
    CommandType.REGISTER_ABILITY.value,
    CommandType.UNREGISTER_ABILITY.value,
    CommandType.LIST_AGENTS.value,
    CommandType.HEALTH_CHECK.value,
    CommandType.DELEGATE.value,
    CommandType.GET_AGENT_INFO.value,
    CommandType.INIT_CLUSTER.value,
    CommandType.SHUTDOWN_CLUSTER.value,
    CommandType.CLUSTER_STATUS.value,
    CommandType.SESSION_CREATE.value,
    CommandType.SESSION_SWITCH.value,
    CommandType.SESSION_LIST.value,
    CommandType.SESSION_ARCHIVE.value,
    CommandType.SESSION_DELETE.value,
})

SESSION_COMMANDS: frozenset[str] = frozenset({
    CommandType.SESSION_CREATE.value,
    CommandType.SESSION_SWITCH.value,
    CommandType.SESSION_LIST.value,
    CommandType.SESSION_ARCHIVE.value,
    CommandType.SESSION_DELETE.value,
})

WORKSPACE_COMMANDS: frozenset[str] = frozenset({
    CommandType.CREATE_WORKSPACE.value,
    CommandType.DESTROY_WORKSPACE.value,
    CommandType.WORKSPACE_SNAPSHOT.value,
    CommandType.WORKSPACE_ROLLBACK.value,
    CommandType.WORKSPACE_DIFF.value,
    CommandType.WORKSPACE_STATUS.value,
})

MANIFEST_COMMANDS: frozenset[str] = frozenset({
    CommandType.MANIFEST_LIST_ABILITIES.value,
    CommandType.MANIFEST_GET_ABILITY.value,
    CommandType.MANIFEST_PUT_ABILITY.value,
    CommandType.MANIFEST_DELETE_ABILITY.value,
    CommandType.MANIFEST_LIST_AGENTS.value,
    CommandType.MANIFEST_GET_AGENT.value,
    CommandType.MANIFEST_PUT_AGENT.value,
    CommandType.MANIFEST_DELETE_AGENT.value,
    CommandType.MANIFEST_RESOLVE_AGENT.value,
    CommandType.MANIFEST_VALIDATE.value,
})

CHAIN_HISTORY_COMMANDS: frozenset[str] = frozenset({
    CommandType.GET_CHAIN_HISTORY.value,
})


# ─── 命令载荷模型 ───


class AgentConfigPayload(BaseModel):
    """Agent 配置载荷，对应 ghrah-core 的 AgentConfig。"""

    name: str
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

    config: AgentConfigPayload
    abilities: list[AbilityDefinitionPayload] | None = None
    manifest_ref: str | None = None


class TerminateAgentPayload(BaseModel):
    """terminate_agent 命令载荷。"""

    name: str


class SendMessagePayload(BaseModel):
    """send_message 命令载荷。"""

    target: str
    content: str
    sender: str = "user"
    timeout: float | None = None


class BroadcastMessagePayload(BaseModel):
    """broadcast_message 命令载荷。"""

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

    agent_name: str
    ability: AbilityDefinitionPayload


class ListAgentsPayload(BaseModel):
    """list_agents 命令载荷（空载荷）。"""

    pass


class HealthCheckPayload(BaseModel):
    """health_check 命令载荷（空载荷）。"""

    pass


class DelegatePayload(BaseModel):
    """delegate 命令载荷。"""

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
    tool_args: dict[str, Any] = Field(default_factory=dict)


class PersistSavePayload(BaseModel):
    """persist_save 命令载荷。

    Core → Subject：请求 Subject 保存持久化数据。
    """

    key: str
    data: dict[str, Any]
    namespace: str = "default"


class PersistLoadPayload(BaseModel):
    """persist_load 命令载荷。

    Core → Subject：请求 Subject 加载持久化数据。
    """

    key: str
    namespace: str = "default"


class PersistDeletePayload(BaseModel):
    """persist_delete 命令载荷。

    Core → Subject：请求 Subject 删除持久化数据。
    """

    key: str
    namespace: str = "default"


class PersistListPayload(BaseModel):
    """persist_list 命令载荷。

    Core → Subject：请求 Subject 列出持久化数据。
    """

    namespace: str = "default"
    prefix: str | None = None


# ─── 事件载荷模型 ───


class AgentSpawnedPayload(BaseModel):
    """agent_spawned 事件载荷。"""

    name: str
    config: AgentConfigPayload


class AgentTerminatedPayload(BaseModel):
    """agent_terminated 事件载荷。"""

    name: str


class AgentResponsePayload(BaseModel):
    """agent_response 事件载荷。"""

    sender: str
    recipient: str
    content: str
    content_blocks: list[dict[str, Any]] | None = None
    message_type: str = "result"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionChainUpdatedPayload(BaseModel):
    """action_chain_updated 事件载荷。"""

    agent_name: str
    node: dict[str, Any] = Field(default_factory=dict)


class AgentErrorPayload(BaseModel):
    """agent_error 事件载荷。"""

    agent_name: str
    error: str


class HealthStatusPayload(BaseModel):
    """health_status 事件载荷。"""

    status: dict[str, bool]


class AbilityResultPayload(BaseModel):
    """ability_result 事件载荷。

    Subject → Core：Ability 执行结果。
    """

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

    promise_id: str
    agent_name: str
    ability_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class HITLResponsePayload(BaseModel):
    """hitl_response 命令载荷。

    Observer → Subject：HITL 审批响应。
    Observer 审批 HITL 请求后发送此消息。
    """

    promise_id: str
    approved: bool
    reason: str | None = None


class UnregisterAbilityPayload(BaseModel):
    """unregister_ability 命令载荷。"""

    agent_name: str
    ability_name: str


class GetAgentInfoPayload(BaseModel):
    """get_agent_info 命令载荷。"""

    name: str


class InitClusterPayload(BaseModel):
    """init_cluster 命令载荷。"""

    config: dict[str, Any] = Field(default_factory=dict)


class ShutdownClusterPayload(BaseModel):
    """shutdown_cluster 命令载荷。"""

    config: dict[str, Any] = Field(default_factory=dict)


class ClusterStatusPayload(BaseModel):
    """cluster_status 命令载荷（空载荷）。"""

    pass


# ─── Workspace 管理载荷模型 ───


class CreateWorkspacePayload(BaseModel):
    """create_workspace 命令载荷。"""

    agent_name: str


class DestroyWorkspacePayload(BaseModel):
    """destroy_workspace 命令载荷。"""

    agent_name: str


class WorkspaceSnapshotPayload(BaseModel):
    """workspace_snapshot 命令载荷。"""

    agent_name: str
    message: str = ""


class WorkspaceRollbackPayload(BaseModel):
    """workspace_rollback 命令载荷。"""

    agent_name: str
    snapshot_id: str


class WorkspaceDiffPayload(BaseModel):
    """workspace_diff 命令载荷。"""

    agent_name: str
    snapshot_id: str | None = None


class WorkspaceStatusPayload(BaseModel):
    """workspace_status 命令载荷。"""

    agent_name: str


# ─── Workspace 事件载荷模型 ───


class WorkspaceCreatedPayload(BaseModel):
    """workspace_created 事件载荷。"""

    agent_name: str
    path: str


class WorkspaceDestroyedPayload(BaseModel):
    """workspace_destroyed 事件载荷。"""

    agent_name: str


class WorkspaceSnapshotCreatedPayload(BaseModel):
    """workspace_snapshot_created 事件载荷。"""

    agent_name: str
    snapshot_id: str
    message: str = ""


class WorkspaceRolledBackPayload(BaseModel):
    """workspace_rolled_back 事件载荷。"""

    agent_name: str
    snapshot_id: str


# ─── Manifest CRUD 载荷模型 ───


class ManifestListPayload(BaseModel):
    """manifest_list_abilities / manifest_list_agents 命令载荷。"""

    namespace: str | None = None


class ManifestGetPayload(BaseModel):
    """manifest_get_ability / manifest_get_agent 命令载荷。"""

    full_name: str


class ManifestPutPayload(BaseModel):
    """manifest_put_ability / manifest_put_agent 命令载荷。"""

    full_name: str
    content: str
    overwrite: bool = False


class ManifestDeletePayload(BaseModel):
    """manifest_delete_ability / manifest_delete_agent 命令载荷。"""

    full_name: str


class ManifestValidatePayload(BaseModel):
    """manifest_validate 命令载荷。"""

    content: str
    manifest_type: str


class ManifestResolvePayload(BaseModel):
    """manifest_resolve_agent 命令载荷。"""

    agent_full_name: str
    runtime_name: str | None = None


# ─── Manifest CRUD 响应载荷模型 ───


class ManifestGetAbilityResponsePayload(BaseModel):
    """manifest_get_ability 响应载荷。"""

    manifest: dict[str, Any]
    source: str


class ManifestGetAgentResponsePayload(BaseModel):
    """manifest_get_agent 响应载荷。"""

    manifest: dict[str, Any]
    source: str


class ManifestPutResponsePayload(BaseModel):
    """manifest_put_ability / manifest_put_agent 响应载荷。"""

    full_name: str


class ManifestDeleteResponsePayload(BaseModel):
    """manifest_delete_ability / manifest_delete_agent 响应载荷。"""

    full_name: str


class ManifestValidateResponsePayload(BaseModel):
    """manifest_validate 响应载荷。"""

    valid: bool
    errors: list[str]


class ManifestResolveAgentResponsePayload(BaseModel):
    """manifest_resolve_agent 响应载荷。"""

    config: dict[str, Any]
    abilities: list[dict[str, Any]]


# ─── Session 命令载荷模型 ───


class SessionCreatePayload(BaseModel):
    """session_create 命令载荷。"""

    agent_name: str
    session_name: str | None = None
    from_node_id: str | None = None
    system_prompt: str | None = None


class SessionSwitchPayload(BaseModel):
    """session_switch 命令载荷。"""

    agent_name: str
    session_id: str


class SessionListPayload(BaseModel):
    """session_list 命令载荷。"""

    agent_name: str


class SessionArchivePayload(BaseModel):
    """session_archive 命令载荷。"""

    agent_name: str
    session_id: str


class SessionDeletePayload(BaseModel):
    """session_delete 命令载荷。"""

    agent_name: str
    session_id: str


class GetChainHistoryPayload(BaseModel):
    """get_chain_history 命令载荷。"""

    agent_name: str
    branch_name: str = "main"
    limit: int = -1


class ChainHistoryResultPayload(BaseModel):
    """get_chain_history 命令的响应载荷。"""

    agent_name: str
    branch_name: str = "main"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    active_session_id: str = ""


# ─── Session 事件载荷模型 ───


class SessionInfoPayload(BaseModel):
    """Session 信息载荷，用于 session 事件和查询结果。"""

    session_id: str
    agent_name: str
    branch_name: str
    state: str = "active"
    head_node_id: str | None = None
    # root_node_id: str | None = None
    parent_session_id: str | None = None
    fork_point_node_id: str | None = None
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0
    iteration_count: int = 0


class SessionCreatedPayload(BaseModel):
    """session_created 事件载荷。"""

    agent_name: str
    session: SessionInfoPayload


class SessionSwitchedPayload(BaseModel):
    """session_switched 事件载荷。"""

    agent_name: str
    session: SessionInfoPayload


class SessionArchivedPayload(BaseModel):
    """session_archived 事件载荷。"""

    agent_name: str
    session_id: str


class SessionDeletedPayload(BaseModel):
    """session_deleted 事件载荷。"""

    agent_name: str
    session_id: str


class SessionListResultPayload(BaseModel):
    """session_list_result 事件载荷。"""

    agent_name: str
    sessions: list[SessionInfoPayload]


# ─── Manifest 事件载荷模型 ───


class ManifestAbilityEventPayload(BaseModel):
    """manifest_ability_created/updated/deleted 事件载荷。"""

    full_name: str
    namespace: str
    manifest: dict[str, Any] | None = None
    source: str | None = None


class ManifestAgentEventPayload(BaseModel):
    """manifest_agent_created/updated/deleted 事件载荷。"""

    full_name: str
    namespace: str
    manifest: dict[str, Any] | None = None
    source: str | None = None


# ─── 系统载荷模型 ───


class CommandResultPayload(BaseModel):
    """command_result 系统载荷。"""

    request_id: str
    success: bool
    data: Any = None
    error: str | None = None


class ErrorPayload(BaseModel):
    """error 系统载荷。"""

    code: str
    message: str
    details: dict[str, Any] | None = None


# ─── 信封模型 ───


class Message(BaseModel):
    """WebSocket 消息信封。

    所有 WebSocket 消息都使用此信封格式传输。

    Attributes:
        type: 消息类型（命令/事件/系统）
        payload: 消息载荷
        request_id: 请求ID，用于关联命令和响应
        timestamp: 消息时间戳（Unix时间戳）
        client_type: 发送方客户端类型（subject/observer），用于连接管理
    """

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    timestamp: float | None = None
    client_type: ClientType | None = None
    seq_id: int | None = None

    def model_dump_with_timestamp(self) -> dict[str, Any]:
        """序列化时自动填充时间戳。"""
        data = self.model_dump()
        if data.get("timestamp") is None:
            data["timestamp"] = time.time()
        return data


def create_command_result(
    request_id: str,
    success: bool,
    data: Any = None,
    error: str | None = None,
) -> Message:
    """创建命令结果消息的便捷函数。"""
    return Message(
        type=SystemType.COMMAND_RESULT.value,
        payload=CommandResultPayload(
            request_id=request_id,
            success=success,
            data=data,
            error=error,
        ).model_dump(),
        request_id=request_id,
    )


def create_event(event_type: EventType, payload: BaseModel) -> Message:
    """创建事件消息的便捷函数。"""
    return Message(
        type=event_type.value,
        payload=payload.model_dump(),
    )


def create_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> Message:
    """创建错误消息的便捷函数。"""
    return Message(
        type=SystemType.ERROR.value,
        payload=ErrorPayload(
            code=code,
            message=message,
            details=details,
        ).model_dump(),
        request_id=request_id,
    )


def create_ping() -> Message:
    """创建心跳 ping 消息。"""
    return Message(type=SystemType.PING.value)


def create_pong() -> Message:
    """创建心跳 pong 消息。"""
    return Message(type=SystemType.PONG.value)


def generate_request_id() -> str:
    """生成唯一的请求ID。"""
    return uuid.uuid4().hex[:12]
