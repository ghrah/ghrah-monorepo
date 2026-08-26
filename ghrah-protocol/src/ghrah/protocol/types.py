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
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)

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
    LIST_CLUSTERS = "list_clusters"

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
    # workspace 一等资源命令（workspace_id 键控；W6）
    WORKSPACE_REGISTER = "workspace_register"
    WORKSPACE_GET = "workspace_get"
    WORKSPACE_LIST = "workspace_list"

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

    # ─── Task 管理类（Observer/Core → Subject）───
    TASK_CREATE = "task_create"
    TASK_UPDATE = "task_update"
    TASK_ASSIGN = "task_assign"
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAIL = "task_fail"
    TASK_CANCEL = "task_cancel"
    TASK_BLOCK = "task_block"
    TASK_LIST = "task_list"
    TASK_GET = "task_get"
    TASK_DELETE = "task_delete"

    # ─── Project 管理类（Observer → Subject，13 个）───
    PROJECT_CREATE = "project_create"
    PROJECT_UPDATE = "project_update"
    PROJECT_LIST = "project_list"
    PROJECT_GET = "project_get"
    PROJECT_DELETE = "project_delete"
    PROJECT_ADD_AGENT = "project_add_agent"
    PROJECT_REMOVE_AGENT = "project_remove_agent"
    PROJECT_LINK_TASK = "project_link_task"
    PROJECT_UNLINK_TASK = "project_unlink_task"
    PROJECT_SET_RECOVERY = "project_set_recovery"
    PROJECT_PAUSE = "project_pause"
    PROJECT_RESUME = "project_resume"
    PROJECT_STOP = "project_stop"

    # ─── Room 管理类（Observer/Core → Subject，10 个）───
    ROOM_CREATE = "room_create"
    ROOM_LIST = "room_list"
    ROOM_GET = "room_get"
    ROOM_UPDATE = "room_update"
    ROOM_DELETE = "room_delete"
    ROOM_JOIN = "room_join"
    ROOM_LEAVE = "room_leave"
    ROOM_GET_MEMBERS = "room_get_members"
    ROOM_GET_LOG = "room_get_log"
    ROOM_SEND = "room_send"

    # ─── 恢复类（Observer → Subject，2 个）───
    RECONCILE_NOW = "reconcile_now"
    RECONCILE_STATUS = "reconcile_status"


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

    # ─── Task 事件（Subject → Observer/Core）───
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_ASSIGNED = "task_assigned"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELED = "task_canceled"
    TASK_BLOCKED = "task_blocked"
    TASK_DELETED = "task_deleted"

    # ─── Project 事件（Subject → Observer，9 个）───
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_DELETED = "project_deleted"
    PROJECT_PAUSED = "project_paused"
    PROJECT_RESUMED = "project_resumed"
    PROJECT_STOPPED = "project_stopped"
    PROJECT_AGENT_ADDED = "project_agent_added"
    PROJECT_AGENT_REMOVED = "project_agent_removed"
    PROJECT_RECOVERY_SET = "project_recovery_set"

    # ─── Room 事件（Subject → Observer/Core，6 个）───
    ROOM_CREATED = "room_created"
    ROOM_UPDATED = "room_updated"
    ROOM_DELETED = "room_deleted"
    ROOM_MEMBER_JOINED = "room_member_joined"
    ROOM_MEMBER_LEFT = "room_member_left"
    ROOM_LOG_APPENDED = "room_log_appended"

    # ─── 恢复事件（Subject → Observer，2 个）───
    SUBJECT_RECONCILED = "subject_reconciled"
    RECONCILE_FAILED = "reconcile_failed"


class TaskStatus(StrEnum):
    """Task lifecycle state."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskPriority(StrEnum):
    """Task priority label."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


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
    CommandType.LIST_CLUSTERS.value,
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
    CommandType.WORKSPACE_REGISTER.value,
    CommandType.WORKSPACE_GET.value,
    CommandType.WORKSPACE_LIST.value,
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

TASK_COMMANDS: frozenset[str] = frozenset({
    CommandType.TASK_CREATE.value,
    CommandType.TASK_UPDATE.value,
    CommandType.TASK_ASSIGN.value,
    CommandType.TASK_START.value,
    CommandType.TASK_COMPLETE.value,
    CommandType.TASK_FAIL.value,
    CommandType.TASK_CANCEL.value,
    CommandType.TASK_BLOCK.value,
    CommandType.TASK_LIST.value,
    CommandType.TASK_GET.value,
    CommandType.TASK_DELETE.value,
})

PROJECT_COMMANDS: frozenset[str] = frozenset({
    CommandType.PROJECT_CREATE.value,
    CommandType.PROJECT_UPDATE.value,
    CommandType.PROJECT_LIST.value,
    CommandType.PROJECT_GET.value,
    CommandType.PROJECT_DELETE.value,
    CommandType.PROJECT_ADD_AGENT.value,
    CommandType.PROJECT_REMOVE_AGENT.value,
    CommandType.PROJECT_LINK_TASK.value,
    CommandType.PROJECT_UNLINK_TASK.value,
    CommandType.PROJECT_SET_RECOVERY.value,
    CommandType.PROJECT_PAUSE.value,
    CommandType.PROJECT_RESUME.value,
    CommandType.PROJECT_STOP.value,
})

ROOM_COMMANDS: frozenset[str] = frozenset({
    CommandType.ROOM_CREATE.value,
    CommandType.ROOM_LIST.value,
    CommandType.ROOM_GET.value,
    CommandType.ROOM_UPDATE.value,
    CommandType.ROOM_DELETE.value,
    CommandType.ROOM_JOIN.value,
    CommandType.ROOM_LEAVE.value,
    CommandType.ROOM_GET_MEMBERS.value,
    CommandType.ROOM_GET_LOG.value,
    CommandType.ROOM_SEND.value,
})

RECONCILE_COMMANDS: frozenset[str] = frozenset({
    CommandType.RECONCILE_NOW.value,
    CommandType.RECONCILE_STATUS.value,
})


# ─── Project 附属枚举 ───


class ProjectStatus(StrEnum):
    """Project lifecycle state（与 ghrah-subject project/models.py 对齐）。"""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class RecoveryAction(StrEnum):
    """恢复动作（on_restart 取值 / reconcile 未知 workspace 处理）。"""

    RESUME = "resume"
    PAUSE = "pause"
    DROP = "drop"


# ─── Room 附属枚举 ───


class RoomSubjectType(StrEnum):
    """Room 成员/作者类型。"""

    AGENT = "agent"
    HUMAN = "human"


class RoomStatus(StrEnum):
    """Room 生命周期状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


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
    metadata: dict[str, Any] | None = None
    """扩展元数据（透传至 AgentMessage.metadata；如 Room 投递写入 room_id）。

    回复归属推导经链节点 messages_delta（receive 侧将 metadata 合入用户
    ChatMessage），非回复消息回传。
    """


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

    Core → Subject → Observer：Core 已确认收到的 Ability 执行结果事件。
    执行结果来源于 Subject 返回的 execute_ability command_result。
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

    agent_name: str
    ability_name: str


class GetAgentInfoPayload(BaseModel):
    """get_agent_info 命令载荷。"""

    name: str


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


class WorkspaceRegisterPayload(BaseModel):
    """workspace_register 命令载荷（把已有目录登记为 workspace）。

    provider_type 为 None 时由 Subject 按 registry.detect 探测规则分派
    （有 .git → git；否则 → plain）。locator 为 file:// URI（MVP）。
    """

    locator: str
    name: str = ""
    provider_type: str | None = None


class WorkspaceGetPayload(BaseModel):
    """workspace_get 命令载荷（workspace_id 键控）。"""

    workspace_id: str


class WorkspaceListPayload(BaseModel):
    """workspace_list 命令载荷（可选 provider_type 过滤）。"""

    provider_type: str | None = None


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
    project_id: str | None = None
    branch_name: str = "main"
    limit: int = -1


class ChainHistoryResultPayload(BaseModel):
    """get_chain_history 命令的响应载荷。"""

    agent_name: str
    branch_name: str = "main"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    active_session_id: str = ""


# ─── Task 命令和事件载荷模型 ───


class TaskInfoPayload(BaseModel):
    """Task 信息载荷，用于 task 命令结果和事件。"""

    task_id: str
    project_id: str
    title: str
    description: str = ""
    agent_name: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    parent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreatePayload(BaseModel):
    """task_create 命令载荷。"""

    title: str
    project_id: str
    description: str = ""
    agent_name: str | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    parent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdatePayload(BaseModel):
    """task_update 命令载荷。"""

    task_id: str
    title: str | None = None
    description: str | None = None
    agent_name: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    parent_id: str | None = None
    dependencies: list[str] | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    metadata_patch: dict[str, Any] | None = None
    expected_version: int | None = None


class TaskIdPayload(BaseModel):
    """task_* 单任务命令载荷。"""

    task_id: str


class TaskAssignPayload(TaskIdPayload):
    """task_assign 命令载荷。"""

    agent_name: str


class TaskCompletePayload(TaskIdPayload):
    """task_complete 命令载荷。"""

    result: Any = None


class TaskFailPayload(TaskIdPayload):
    """task_fail 命令载荷。"""

    error: str


class TaskCancelPayload(TaskIdPayload):
    """task_cancel 命令载荷。"""

    reason: str | None = None


class TaskBlockPayload(TaskIdPayload):
    """task_block 命令载荷。"""

    reason: str | None = None


class TaskListPayload(BaseModel):
    """task_list 命令载荷。"""

    agent_name: str | None = None
    status: TaskStatus | list[TaskStatus] | None = None
    parent_id: str | None = None
    project_id: str | None = None
    include_terminal: bool = True
    limit: int = 100


class TaskDeletePayload(TaskIdPayload):
    """task_delete 命令载荷。"""

    force: bool = False


class TaskListResultPayload(BaseModel):
    """task_list 命令响应载荷。"""

    tasks: list[TaskInfoPayload] = Field(default_factory=list)
    count: int = 0


class TaskEventPayload(BaseModel):
    """task_* 事件载荷。"""

    task: TaskInfoPayload
    previous_status: TaskStatus | None = None
    reason: str | None = None


# ─── Project 载荷模型 ───


class PathGrantSchema(BaseModel):
    """Agent 对某 workspace 子路径的访问授权。"""

    workspace_id: str
    subpath: str = "."


class WorkspaceMountSchema(BaseModel):
    """Project 挂载的 workspace（对齐 ghrah-subject project/models.WorkspaceMount）。"""

    workspace_id: str
    role: str | None = None
    default_for_agents: bool = False


class WritableWorkspaceSpec(BaseModel):
    """project_create 时登记的默认批准读写 Workspace。"""

    locator: str
    name: str = ""
    role: str | None = None
    default_for_agents: bool = False


class AgentSpecSchema(BaseModel):
    """Project 内 agent desired-state 摘要。"""

    name: str
    cluster_id: str
    manifest_ref: str = ""
    instance_manifest_path: str = ""
    system_prompt: str = ""
    abilities: list[str] | None = None
    path_grants: list[PathGrantSchema] = Field(default_factory=list)


class ProjectInfoPayload(BaseModel):
    """Project 信息基类载荷。

    对齐 ghrah-subject project/models.ProjectRecord，用于 project_get/project_list
    结果项及 PROJECT_* 事件回执。version/deleted_at/cluster_ids/workspaces/
    project_root_locator 为 Subject 独占内部状态 Root；workspaces 为 Agent 工作资源。
    Project 内部存储位置统一由 ``project_root_locator`` 派生。
    """

    project_id: str
    name: str
    description: str = ""
    project_root_locator: str = ""
    manifest_ref: str = ""
    cluster_ids: list[str] = Field(default_factory=list)
    workspaces: list[WorkspaceMountSchema] = Field(default_factory=list)
    agents: list[AgentSpecSchema] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    status: ProjectStatus = ProjectStatus.ACTIVE
    recovery: str = RecoveryAction.RESUME.value
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    deleted_at: str | None = None


class ProjectCreatePayload(BaseModel):
    """project_create 命令载荷。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    project_root_locator: str = ""
    writable_workspaces: list[WritableWorkspaceSpec] = Field(default_factory=list)
    manifest_ref: str = ""
    recovery: str = RecoveryAction.RESUME.value


class ProjectUpdatePayload(BaseModel):
    """project_update 命令载荷（乐观锁）。"""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    name: str | None = None
    description: str | None = None
    manifest_ref: str | None = None
    expected_version: int | None = None


class ProjectIdPayload(BaseModel):
    """project_get / project_delete / project_pause / project_resume /
    project_stop 命令载荷（project_id 键控）。"""

    project_id: str


class ProjectDeletePayload(ProjectIdPayload):
    """project_delete 命令载荷。"""

    force: bool = False
    purge_storage: bool = False


class ProjectListPayload(BaseModel):
    """project_list 命令载荷（可选 status 过滤；MVP 不分页）。"""

    status: ProjectStatus | None = None
    include_deleted: bool = False


class ProjectAddAgentPayload(BaseModel):
    """project_add_agent 命令载荷。"""

    project_id: str
    agent: AgentSpecSchema
    expected_version: int | None = None


class ProjectRemoveAgentPayload(BaseModel):
    """project_remove_agent 命令载荷。"""

    project_id: str
    agent_name: str
    expected_version: int | None = None


class ProjectLinkTaskPayload(BaseModel):
    """project_link_task 命令载荷。"""

    project_id: str
    task_id: str
    expected_version: int | None = None


class ProjectUnlinkTaskPayload(BaseModel):
    """project_unlink_task 命令载荷。"""

    project_id: str
    task_id: str
    expected_version: int | None = None


class ProjectSetRecoveryPayload(ProjectIdPayload):
    """project_set_recovery 命令载荷。"""

    recovery: RecoveryAction = RecoveryAction.RESUME
    expected_version: int | None = None


class ProjectListResultPayload(BaseModel):
    """project_list 命令结果载荷。"""

    projects: list[ProjectInfoPayload] = Field(default_factory=list)
    count: int = 0


class ReconcileNowPayload(BaseModel):
    """reconcile_now 命令载荷（触发一次 reconcile）。"""

    subject_id: str = "default"


class ReconcileStatusPayload(BaseModel):
    """reconcile_status 命令载荷（查询最近一次 reconcile 报告）。"""

    subject_id: str = "default"


# ─── Project 事件载荷模型 ───


class ProjectEventPayload(BaseModel):
    """project_* 事件载荷（created/updated/deleted/paused/resumed/stopped/
    recovery_set 通用基类）。

    携带变更后全量 ProjectInfoPayload 快照，Observer 据此更新本地 store。
    """

    project: ProjectInfoPayload


class ProjectAgentEventPayload(BaseModel):
    """project_agent_added / project_agent_removed 事件载荷。"""

    project: ProjectInfoPayload
    agent_name: str


class ReconcileReportPayload(BaseModel):
    """subject_reconciled / reconcile_failed 事件载荷（reconcile 报告摘要）。"""

    subject_id: str
    success: bool
    projects_reconciled: int = 0
    agents_spawned: int = 0
    workspaces_adopted: int = 0
    errors: list[str] = Field(default_factory=list)
    bootstrap: bool = False
    paused: int = 0
    dropped: int = 0
    tasks_migrated: int = 0


# ─── Room 载荷模型 ───


class RoomMember(BaseModel):
    """Room 成员（多对多：agent / human 均可为成员）。"""

    subject: str
    subject_type: RoomSubjectType
    joined_at: str = ""


class RoomInfoPayload(BaseModel):
    """Room 信息载荷（room_get/room_list 结果项及 ROOM_* 事件回执）。

    对齐 ghrah-subject room/models.RoomRecord；seq_watermark 为该 room
    已分配的最大 RoomLog seq（Subject 单点分配）。
    """

    room_id: str
    project_id: str
    name: str
    status: RoomStatus = RoomStatus.ACTIVE
    members: list[RoomMember] = Field(default_factory=list)
    seq_watermark: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class RoomLogEntryPayload(BaseModel):
    """RoomLog 节点载荷 = 最小信封 + 自由 map（不预置业务枚举 schema）。"""

    id: str
    room_id: str
    seq: int
    author: str
    author_type: RoomSubjectType
    timestamp: float
    data: dict[str, Any] = Field(default_factory=dict)


class RoomCreatePayload(BaseModel):
    """room_create 命令载荷。"""

    project_id: str
    name: str


class RoomListPayload(BaseModel):
    """room_list 命令载荷（可选 project/status 过滤）。"""

    project_id: str | None = None
    status: RoomStatus | None = None


class RoomIdPayload(BaseModel):
    """room_get / room_update / room_delete / room_get_members /
    room_get_log / room_send 等命令的 room_id 键控基类。"""

    room_id: str


class RoomUpdatePayload(BaseModel):
    """room_update 命令载荷（乐观锁）。"""

    room_id: str
    name: str | None = None
    expected_version: int | None = None


class RoomDeletePayload(RoomIdPayload):
    """room_delete 命令载荷。"""

    force: bool = False


class RoomJoinPayload(BaseModel):
    """room_join 命令载荷。"""

    room_id: str
    subject: str
    subject_type: RoomSubjectType


class RoomLeavePayload(BaseModel):
    """room_leave 命令载荷。"""

    room_id: str
    subject: str


class RoomGetLogPayload(BaseModel):
    """room_get_log 命令载荷（since_seq 增量 / limit 截尾）。"""

    room_id: str
    since_seq: int | None = None
    limit: int = 100


class RoomSendPayload(BaseModel):
    """room_send 命令载荷（人类/Mock 公开路径；agent 路径由 Core send
    ability 解析后经同一命令面收敛，见 Room 计划附录双调用方分流）。"""

    room_id: str
    author: str
    author_type: RoomSubjectType
    data: dict[str, Any] = Field(default_factory=dict)


class RoomListResultPayload(BaseModel):
    """room_list 命令结果载荷。"""

    rooms: list[RoomInfoPayload] = Field(default_factory=list)
    count: int = 0


class RoomLogResultPayload(BaseModel):
    """room_get_log 命令结果载荷。"""

    entries: list[RoomLogEntryPayload] = Field(default_factory=list)
    count: int = 0


# ─── Room 事件载荷模型 ───


class RoomEventPayload(BaseModel):
    """room_created / room_updated 事件载荷（全量快照）。"""

    room: RoomInfoPayload


class RoomDeletedEventPayload(BaseModel):
    """room_deleted 事件载荷。"""

    room_id: str
    project_id: str


class RoomMemberEventPayload(BaseModel):
    """room_member_joined / room_member_left 事件载荷。

    joined 携带 member；left 仅 subject（成员已移出全量快照）。
    """

    room: RoomInfoPayload
    member: RoomMember | None = None
    subject: str | None = None


class RoomLogEventPayload(BaseModel):
    """room_log_appended 事件载荷。"""

    entry: RoomLogEntryPayload


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


class Envelope(BaseModel):
    """WebSocket 消息信封（非泛型，宽类型）。

    payload 在 wire 层保持 Any（dict | BaseModel 实例 | None）。
    类型安全通过 PAYLOAD_MAP + envelope_from_dict（入口收窄）
    + expect_payload（handler 边界断言）实现，不由 Pydantic 泛型承担。

    type 保持 str（不收紧为 MessageType union），以接受未知 type
    字符串、保持前向兼容；由 known_type() / as_command_type() 判断。

    Attributes:
        type: 消息类型字符串（命令/事件/系统）
        payload: 消息载荷（dict / BaseModel 实例 / None）
        request_id: 请求ID，用于关联命令和响应
        timestamp: 消息时间戳（Unix时间戳）
        client_type: 发送方客户端类型（subject/observer），用于连接管理
        seq_id: 单调递增序号（广播时填充）
    """

    type: str
    payload: Any = Field(default_factory=dict)
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

    # ── 类型辅助（不改变 wire，仅消费侧便利）──

    def known_type(self) -> bool:
        """type 是否在 PAYLOAD_MAP 中（已知命令/事件）。"""
        return self.type in PAYLOAD_MAP

    def as_command_type(self) -> CommandType | None:
        """尝试解析为 CommandType（未知返回 None，不抛）。"""
        try:
            return CommandType(self.type)
        except ValueError:
            return None

    def as_event_type(self) -> EventType | None:
        """尝试解析为 EventType（未知返回 None，不抛）。"""
        try:
            return EventType(self.type)
        except ValueError:
            return None

    def as_system_type(self) -> SystemType | None:
        """尝试解析为 SystemType（未知返回 None，不抛）。"""
        try:
            return SystemType(self.type)
        except ValueError:
            return None


# ─── type → Payload 注册表 ───
#
# 仅登记 schema 正确且当前有消费方的 payload。
# - persist_*（13 个）不登记：PersistSavePayload 等 schema 与实际 wire shape 不符，
#   留待 Stage 2（Subject 插件化）补齐真实 payload。此处 payload 保持裸 dict 透传。
# - command_result / error / ping / pong 不登记：welcome 包手写 payload 与
#   CommandResultPayload schema 不符（见 S1.2.5）。此处 payload 保持裸 dict。

COMMAND_PAYLOAD_MAP: dict[CommandType, type[BaseModel]] = {
    CommandType.SPAWN_AGENT: SpawnAgentPayload,
    CommandType.TERMINATE_AGENT: TerminateAgentPayload,
    CommandType.SEND_MESSAGE: SendMessagePayload,
    CommandType.BROADCAST_MESSAGE: BroadcastMessagePayload,
    CommandType.EXECUTE_ABILITY: ExecuteAbilityPayload,
    CommandType.REGISTER_ABILITY: RegisterAbilityPayload,
    CommandType.UNREGISTER_ABILITY: UnregisterAbilityPayload,
    CommandType.LIST_AGENTS: ListAgentsPayload,
    CommandType.HEALTH_CHECK: HealthCheckPayload,
    CommandType.DELEGATE: DelegatePayload,
    CommandType.SUBSCRIBE: SubscribePayload,
    CommandType.UNSUBSCRIBE: UnsubscribePayload,
    CommandType.GET_AGENT_INFO: GetAgentInfoPayload,
    CommandType.INIT_CLUSTER: InitClusterPayload,
    CommandType.SHUTDOWN_CLUSTER: ShutdownClusterPayload,
    CommandType.CLUSTER_STATUS: ClusterStatusPayload,
    CommandType.LIST_CLUSTERS: ListClustersPayload,
    CommandType.HITL_RESPONSE: HITLResponsePayload,
    # persist_*: payload 为裸 dict（Stage 2 补齐真实 payload 模型）
    # workspace_* / manifest_* / get_chain_history: payload 模型存在但消费侧
    #   仍以 dict 委托 SubjectService，本阶段不登记以保持现状（Stage 2 评估）
    # Task 管理（11 个）
    CommandType.TASK_CREATE: TaskCreatePayload,
    CommandType.TASK_UPDATE: TaskUpdatePayload,
    CommandType.TASK_ASSIGN: TaskAssignPayload,
    CommandType.TASK_START: TaskIdPayload,
    CommandType.TASK_COMPLETE: TaskCompletePayload,
    CommandType.TASK_FAIL: TaskFailPayload,
    CommandType.TASK_CANCEL: TaskCancelPayload,
    CommandType.TASK_BLOCK: TaskBlockPayload,
    CommandType.TASK_LIST: TaskListPayload,
    CommandType.TASK_GET: TaskIdPayload,
    CommandType.TASK_DELETE: TaskDeletePayload,
    # Session 管理（5 个）
    CommandType.SESSION_CREATE: SessionCreatePayload,
    CommandType.SESSION_SWITCH: SessionSwitchPayload,
    CommandType.SESSION_LIST: SessionListPayload,
    CommandType.SESSION_ARCHIVE: SessionArchivePayload,
    CommandType.SESSION_DELETE: SessionDeletePayload,
    # Project 管理（13 个）
    CommandType.PROJECT_CREATE: ProjectCreatePayload,
    CommandType.PROJECT_UPDATE: ProjectUpdatePayload,
    CommandType.PROJECT_LIST: ProjectListPayload,
    CommandType.PROJECT_GET: ProjectIdPayload,
    CommandType.PROJECT_DELETE: ProjectDeletePayload,
    CommandType.PROJECT_ADD_AGENT: ProjectAddAgentPayload,
    CommandType.PROJECT_REMOVE_AGENT: ProjectRemoveAgentPayload,
    CommandType.PROJECT_LINK_TASK: ProjectLinkTaskPayload,
    CommandType.PROJECT_UNLINK_TASK: ProjectUnlinkTaskPayload,
    CommandType.PROJECT_SET_RECOVERY: ProjectSetRecoveryPayload,
    CommandType.PROJECT_PAUSE: ProjectIdPayload,
    CommandType.PROJECT_RESUME: ProjectIdPayload,
    CommandType.PROJECT_STOP: ProjectIdPayload,
    # Room 管理（10 个）
    CommandType.ROOM_CREATE: RoomCreatePayload,
    CommandType.ROOM_LIST: RoomListPayload,
    CommandType.ROOM_GET: RoomIdPayload,
    CommandType.ROOM_UPDATE: RoomUpdatePayload,
    CommandType.ROOM_DELETE: RoomDeletePayload,
    CommandType.ROOM_JOIN: RoomJoinPayload,
    CommandType.ROOM_LEAVE: RoomLeavePayload,
    CommandType.ROOM_GET_MEMBERS: RoomIdPayload,
    CommandType.ROOM_GET_LOG: RoomGetLogPayload,
    CommandType.ROOM_SEND: RoomSendPayload,
    # 恢复（2 个）
    CommandType.RECONCILE_NOW: ReconcileNowPayload,
    CommandType.RECONCILE_STATUS: ReconcileStatusPayload,
}

EVENT_PAYLOAD_MAP: dict[EventType, type[BaseModel]] = {
    EventType.AGENT_SPAWNED: AgentSpawnedPayload,
    EventType.AGENT_TERMINATED: AgentTerminatedPayload,
    EventType.AGENT_RESPONSE: AgentResponsePayload,
    EventType.ACTION_CHAIN_UPDATED: ActionChainUpdatedPayload,
    EventType.AGENT_ERROR: AgentErrorPayload,
    EventType.HEALTH_STATUS: HealthStatusPayload,
    EventType.ABILITY_RESULT: AbilityResultPayload,
    EventType.HITL_REQUEST: HITLRequestPayload,
    EventType.WORKSPACE_CREATED: WorkspaceCreatedPayload,
    EventType.WORKSPACE_DESTROYED: WorkspaceDestroyedPayload,
    EventType.WORKSPACE_SNAPSHOT_CREATED: WorkspaceSnapshotCreatedPayload,
    EventType.WORKSPACE_ROLLED_BACK: WorkspaceRolledBackPayload,
    EventType.SESSION_CREATED: SessionCreatedPayload,
    EventType.SESSION_SWITCHED: SessionSwitchedPayload,
    EventType.SESSION_ARCHIVED: SessionArchivedPayload,
    EventType.SESSION_DELETED: SessionDeletedPayload,
    EventType.SESSION_LIST_RESULT: SessionListResultPayload,
    # task_* 事件（9 个）payload 模型 TaskEventPayload 已存在
    EventType.TASK_CREATED: TaskEventPayload,
    EventType.TASK_UPDATED: TaskEventPayload,
    EventType.TASK_ASSIGNED: TaskEventPayload,
    EventType.TASK_STARTED: TaskEventPayload,
    EventType.TASK_COMPLETED: TaskEventPayload,
    EventType.TASK_FAILED: TaskEventPayload,
    EventType.TASK_CANCELED: TaskEventPayload,
    EventType.TASK_BLOCKED: TaskEventPayload,
    EventType.TASK_DELETED: TaskEventPayload,
    # manifest_* 事件 payload 模型存在
    EventType.MANIFEST_ABILITY_CREATED: ManifestAbilityEventPayload,
    EventType.MANIFEST_ABILITY_UPDATED: ManifestAbilityEventPayload,
    EventType.MANIFEST_ABILITY_DELETED: ManifestAbilityEventPayload,
    EventType.MANIFEST_AGENT_CREATED: ManifestAgentEventPayload,
    EventType.MANIFEST_AGENT_UPDATED: ManifestAgentEventPayload,
    EventType.MANIFEST_AGENT_DELETED: ManifestAgentEventPayload,
    # Project 事件（9 个）
    EventType.PROJECT_CREATED: ProjectEventPayload,
    EventType.PROJECT_UPDATED: ProjectEventPayload,
    EventType.PROJECT_DELETED: ProjectEventPayload,
    EventType.PROJECT_PAUSED: ProjectEventPayload,
    EventType.PROJECT_RESUMED: ProjectEventPayload,
    EventType.PROJECT_STOPPED: ProjectEventPayload,
    EventType.PROJECT_AGENT_ADDED: ProjectAgentEventPayload,
    EventType.PROJECT_AGENT_REMOVED: ProjectAgentEventPayload,
    EventType.PROJECT_RECOVERY_SET: ProjectEventPayload,
    # Room 事件（6 个）
    EventType.ROOM_CREATED: RoomEventPayload,
    EventType.ROOM_UPDATED: RoomEventPayload,
    EventType.ROOM_DELETED: RoomDeletedEventPayload,
    EventType.ROOM_MEMBER_JOINED: RoomMemberEventPayload,
    EventType.ROOM_MEMBER_LEFT: RoomMemberEventPayload,
    EventType.ROOM_LOG_APPENDED: RoomLogEventPayload,
    # 恢复事件（2 个）
    EventType.SUBJECT_RECONCILED: ReconcileReportPayload,
    EventType.RECONCILE_FAILED: ReconcileReportPayload,
}

PAYLOAD_MAP: dict[str, type[BaseModel]] = {
    **{k.value: v for k, v in COMMAND_PAYLOAD_MAP.items()},
    **{k.value: v for k, v in EVENT_PAYLOAD_MAP.items()},
    # command_result / error / ping / pong 不登记（见模块注释）
}


def envelope_from_dict(data: dict[str, Any]) -> Envelope:
    """从 dict 反序列化为 Envelope（唯一反序列化入口）。

    wire 信封保持宽（payload: Any）。已知 type → 查 PAYLOAD_MAP 收窄为对应
    Pydantic 模型实例；未知 type / 无 payload / 未登记 → payload 保持裸 dict
    （前向兼容，不崩）。

    Args:
        data: 原始 wire dict（来自 websocket receive_json）

    Returns:
        Envelope 实例。已知 type 时 payload 为对应 BaseModel 实例，
        否则 payload 为裸 dict（或原始值）。
    """
    msg_type = data.get("type", "")
    payload_cls = PAYLOAD_MAP.get(msg_type)
    raw_payload = data.get("payload", {})
    if payload_cls is not None and isinstance(raw_payload, dict):
        payload = payload_cls.model_validate(raw_payload)
    else:
        payload = raw_payload
    return Envelope(
        type=msg_type,
        payload=payload,
        request_id=data.get("request_id"),
        timestamp=data.get("timestamp"),
        client_type=data.get("client_type"),
        seq_id=data.get("seq_id"),
    )


def expect_payload(msg: Envelope, cls: type[T]) -> T:
    """在 handler 边界把 payload 断言为具体类型。

    若 payload 已是该类型（经 envelope_from_dict 收窄）直接返回；
    若是 dict（未登记 MAP / 旧路径）则 model_validate 收窄；
    校验失败抛 ValidationError（暴露 wire/schema 不符，比静默 .get() 更好）。

    Args:
        msg: 收到的消息信封
        cls: 期望的 payload 类型

    Returns:
        具体类型的 payload 实例

    Raises:
        pydantic.ValidationError: payload 与 cls 不符
    """
    if isinstance(msg.payload, cls):
        return msg.payload
    return cls.model_validate(msg.payload)


def payload_agent_name(payload: Any) -> str | None:
    """提取订阅过滤使用的 agent_name。

    保持旧 wire 行为：订阅过滤只认 payload["agent_name"]。
    缺失 agent_name 时返回 None，ConnectionManager 将其解释为不过滤
    agent、广播给所有匹配 event_type 的连接。
    """
    if isinstance(payload, BaseModel):
        val = getattr(payload, "agent_name", None)
        return val if isinstance(val, str) and val else None
    if isinstance(payload, dict):
        val = payload.get("agent_name")
        return val if isinstance(val, str) and val else None
    return None


# ─── 工厂函数（payload 存模型实例，序列化由 model_dump 统一处理）───


def create_command_result(
    request_id: str,
    success: bool,
    data: Any = None,
    error: str | None = None,
) -> Envelope:
    """创建命令结果消息的便捷函数。"""
    return Envelope(
        type=SystemType.COMMAND_RESULT.value,
        payload=CommandResultPayload(
            request_id=request_id,
            success=success,
            data=data,
            error=error,
        ),
        request_id=request_id,
    )


def create_event(event_type: EventType, payload: BaseModel) -> Envelope:
    """创建事件消息的便捷函数。"""
    return Envelope(
        type=event_type.value,
        payload=payload,
    )


def create_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> Envelope:
    """创建错误消息的便捷函数。"""
    return Envelope(
        type=SystemType.ERROR.value,
        payload=ErrorPayload(
            code=code,
            message=message,
            details=details,
        ),
        request_id=request_id,
    )


def create_ping() -> Envelope:
    """创建心跳 ping 消息。"""
    return Envelope(type=SystemType.PING.value)


def create_pong() -> Envelope:
    """创建心跳 pong 消息。"""
    return Envelope(type=SystemType.PONG.value)


def generate_request_id() -> str:
    """生成唯一的请求ID。"""
    return uuid.uuid4().hex[:12]


# Message = Envelope 别名（向后兼容；新代码应直接使用 Envelope）。
# 因 Envelope 非泛型，别名稳定，不再绑定泛型参数。
Message = Envelope
