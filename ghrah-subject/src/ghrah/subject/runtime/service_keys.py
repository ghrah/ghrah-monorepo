# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Typed service keys and runtime service contracts for Subject units."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from ghrah.manifest.types import PermissionFlags  # type: ignore[import-untyped]
from ghrah.subject.hitl.notary import HITLNotary
from ghrah.subject.hitl.policy import HITLPolicy
from ghrah.subject.ledger.chain import ActionChainLedger
from ghrah.subject.manifest_store.store import ManifestStore
from ghrah.subject.persistence.service import SubjectPersistenceService
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.sandbox.workspace import WorkspaceManager
from ghrah.subject.task.store import TaskStore
from ghrah.subject.transport.observer import ObserverEndpoint
from ghrah.subject.workspace.models import WorkspaceRecord

if TYPE_CHECKING:
    from ghrah.protocol.types import SpawnAgentPayload
    from ghrah.subject.project.models import AgentSpec, ProjectRecord

__all__ = [
    "ABILITY_EXECUTOR",
    "CAPABILITY_REGISTRY",
    "CLUSTER_TRANSPORT_MANAGER",
    "COMMAND_BRIDGE",
    "COMMAND_RUNNER",
    "CORE_CLUSTER_REGISTRY",
    "DESIRED_STATE_STORE",
    "EVENT_BRIDGE",
    "HITL_POLICY",
    "HITL_NOTARY",
    "LEDGER",
    "MANIFEST_PERMISSION_INDEX",
    "MANIFEST_STORE",
    "MCP_CLIENT_REGISTRY",
    "OBSERVER_ENDPOINT",
    "OBSERVER_EVENT_BUS",
    "PERMISSION_SERVICE",
    "PERSISTENCE",
    "PROJECT_MANAGER",
    "RECONCILIATION_SERVICE",
    "SANDBOX_EXECUTOR",
    "SESSION_REGISTRY",
    "TASK_MANAGER",
    "TASK_STORE",
    "WORKSPACE_MANAGER",
    "WORKSPACE_SERVICE",
    "AbilityExecutor",
    "ClusterHandle",
    "ClusterTransportManager",
    "CommandRunner",
    "CoreClusterRegistryService",
    "ManifestPermissionIndex",
    "ObserverEventBus",
    "PermissionService",
    "ProjectManagerService",
    "SubjectServiceKey",
    "TaskManagerService",
    "WorkspaceService",
]

T = TypeVar("T")


@dataclass(frozen=True)
class SubjectServiceKey(Generic[T]):
    """Typed key for values stored in :class:`SubjectServices`."""

    name: str
    service_type: type[Any] | tuple[type[Any], ...] = object


class WorkspaceService(Protocol):
    """Workspace contract required by runtime units.

    旧名作桥、新名叠加：
    - ``resolve_agent_path`` 保留为兼容桥（现有生产调用方零改动）；
    - ``resolve_agent_default_path`` 新名叠加，语义对齐旧名但以 WorkspaceRecord 取向，
      是 Stage B agent active workspace 切换的对接点；
    - ``get_workspace_record`` workspace_id 键控一等查询（W6 新命令对接点）。
    """

    @property
    def root_path(self) -> str:
        """Return the workspace root path."""

    async def create_workspace(self, agent_name: str) -> Any:
        """Create or return a workspace for an agent."""

    def resolve_agent_path(self, agent_name: str) -> str | None:
        """Resolve an agent name to its workspace path, if present.

        兼容桥：返回 agent 默认 workspace 的路径；含原「manager 无记录但磁盘存在
        目录」的回退行为。保留旧名，现有生产调用方零改动。
        """

    def resolve_agent_default_path(self, agent_name: str) -> str | None:
        """Resolve an agent name to its default workspace path (new name overlay).

        语义对齐 ``resolve_agent_path``，以 WorkspaceRecord 取向；Stage B agent
        active workspace 切换的对接点。默认实现可回退到 ``resolve_agent_path``。
        """

    def get_workspace_record(self, workspace_id: str) -> WorkspaceRecord | None:
        """Return the WorkspaceRecord for a workspace_id, if registered."""


class ManifestPermissionIndex(Protocol):
    """Dynamic view of manifest-derived permission flags."""

    def get_permissions(self) -> dict[str, PermissionFlags]:
        """Return the current ability permission index."""


class PermissionService(Protocol):
    """Permission decision service used by ability execution units."""

    def check_ability(
        self,
        ability_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> Any:
        """Check whether an ability invocation is permitted."""


class CommandRunner(Protocol):
    """Command execution contract used by sandbox-facing units."""

    async def run_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Run a command and return an implementation-defined result."""


class AbilityExecutor(Protocol):
    """Ability execution contract exposed to runtime dispatch."""

    async def execute_ability(
        self,
        agent_name: str,
        ability_name: str,
        tool_args: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an ability for an agent."""


class TaskManagerService(Protocol):
    """Task command orchestration contract exposed to runtime dispatch.

    Surfaces a single ``handle_command`` entry point so that other units
    (e.g. Stage 4 DelegationAbility) can invoke task management without a
    compile-time dependency on the concrete :class:`TaskManager`.
    """

    async def handle_command(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch a task command. Returns a dispatcher-shape result dict."""


class ProjectManagerService(Protocol):
    """Project command orchestration contract exposed to runtime dispatch.

    ``handle_command`` 透传 13 个 project 命令；``bootstrap_default_project`` /
    ``adopt_existing_agents`` 为 S4.6 reconcile 首启 bootstrap 专用高层方法
    （决策 2，避免 reconciler 直调底层 store）。
    """

    async def handle_command(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch a project command. Returns a dispatcher-shape result dict."""

    async def bootstrap_default_project(self) -> ProjectRecord:
        """建 default project（default cluster + default workspace + init_cluster）
        并 ProjectStore.upsert，返回记录。供 reconcile 首启 bootstrap。"""

    async def adopt_existing_agents(
        self, project_id: str, cluster_id: str
    ) -> list[AgentSpec]:
        """经 cluster_transport.list_agents 从 Core 取现有 agent，构造 AgentSpec
        并加入 project.agents desired-state，返回列表。"""


class ClusterHandle(Protocol):
    """单 cluster 的 Core 接入转发契约（spawn/terminate/list_agents）。"""

    @property
    def is_connected(self) -> bool:
        """该 handle 的 transport 是否已连接。"""

    async def spawn_agent(self, payload: SpawnAgentPayload) -> dict[str, Any]:
        """发 spawn_agent，返回 command_result dict。"""

    async def list_agents(self) -> list[dict[str, Any]]:
        """发 list_agents，返回 agent 信息列表。"""

    async def terminate_agent(self, agent_name: str) -> dict[str, Any]:
        """发 terminate_agent，返回 command_result dict。"""

    async def shutdown(self) -> None:
        """fire-and-forget 发 shutdown_cluster。"""


class ClusterTransportManager(Protocol):
    """per-cluster WS transport 句柄管理契约。"""

    async def ensure_cluster(self, cluster_id: str) -> ClusterHandle:
        """幂等建/取某 cluster 的 handle。"""

    def get_handle(self, cluster_id: str) -> ClusterHandle:
        """取已建 handle；不存在 raise KeyError。"""

    def has_cluster(self, cluster_id: str) -> bool:
        """某 cluster handle 是否已建。"""

    async def shutdown_cluster(self, cluster_id: str) -> None:
        """shutdown 某 cluster。"""

    async def stop(self) -> None:
        """关闭所有 handle 的 transport。"""


class CoreClusterRegistryService(Protocol):
    """cluster = CoreUnit 实例注册表契约（进程内运行时挂载/卸载）。"""

    async def ensure_cluster(self, cluster_id: str) -> ClusterHandle:
        """幂等挂载/取某 cluster 的 CoreUnit 实例 handle。"""

    def get_handle(self, cluster_id: str) -> ClusterHandle:
        """取已挂载 handle；不存在 raise KeyError。"""

    def has_cluster(self, cluster_id: str) -> bool:
        """某 cluster 实例是否已挂载。"""

    async def shutdown_cluster(self, cluster_id: str) -> None:
        """dispose 某 cluster 的 fiber（handle 失效）。"""

    async def stop(self) -> None:
        """dispose 全部 cluster（unit.stop 时调用）。"""


class ObserverEventBus(Protocol):
    """Observer-facing event bridge contract."""

    async def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        """Publish an event to observer sessions."""

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        """Subscribe an observer session."""


class _ReservedService(Protocol):
    """Placeholder protocol for services planned after Stage 2."""


WORKSPACE_SERVICE = SubjectServiceKey[WorkspaceService]("workspace_service")
WORKSPACE_MANAGER = SubjectServiceKey[WorkspaceManager]("workspace_manager", WorkspaceManager)
COMMAND_RUNNER = SubjectServiceKey[CommandRunner]("command_runner")
PERSISTENCE = SubjectServiceKey[SubjectPersistenceService](
    "persistence",
    SubjectPersistenceService,
)
LEDGER = SubjectServiceKey[ActionChainLedger]("ledger", ActionChainLedger)
SANDBOX_EXECUTOR = SubjectServiceKey[SandboxExecutor]("sandbox_executor", SandboxExecutor)
MANIFEST_STORE = SubjectServiceKey[ManifestStore]("manifest_store", ManifestStore)
MANIFEST_PERMISSION_INDEX = SubjectServiceKey[ManifestPermissionIndex](
    "manifest_permission_index"
)
PERMISSION_SERVICE = SubjectServiceKey[PermissionService]("permission_service")
HITL_POLICY = SubjectServiceKey[HITLPolicy]("hitl_policy", HITLPolicy)
HITL_NOTARY = SubjectServiceKey[HITLNotary]("hitl_notary", HITLNotary)
OBSERVER_ENDPOINT = SubjectServiceKey[ObserverEndpoint]("observer_endpoint")
OBSERVER_EVENT_BUS = SubjectServiceKey[ObserverEventBus]("observer_event_bus")
CAPABILITY_REGISTRY = SubjectServiceKey[CapabilityRegistry](
    "capability_registry",
    CapabilityRegistry,
)
ABILITY_EXECUTOR = SubjectServiceKey[AbilityExecutor]("ability_executor")
TASK_MANAGER = SubjectServiceKey[TaskManagerService]("task_manager")
TASK_STORE = SubjectServiceKey[TaskStore]("task_store", TaskStore)
CLUSTER_TRANSPORT_MANAGER = SubjectServiceKey[ClusterTransportManager](
    "cluster_transport_manager"
)
CORE_CLUSTER_REGISTRY = SubjectServiceKey[CoreClusterRegistryService](
    "core_cluster_registry"
)
PROJECT_MANAGER = SubjectServiceKey[ProjectManagerService]("project_manager")

# Reserved for Stage 3+ integrations. The keys are intentionally real so
# dependency declarations can be written before the concrete services exist.
MCP_CLIENT_REGISTRY = SubjectServiceKey[_ReservedService]("mcp_client_registry")
SESSION_REGISTRY = SubjectServiceKey[_ReservedService]("session_registry")
COMMAND_BRIDGE = SubjectServiceKey[Callable[..., Awaitable[Any]]]("command_bridge")
EVENT_BRIDGE = SubjectServiceKey[Callable[..., Awaitable[Any]]]("event_bridge")


# recovery 服务键置于文件末尾：DesiredStateStore / ReconciliationService 为
# Stage 4 新建具体类，置于末尾导入避免循环（recovery 模块本身不 import 本模块，
# 经 unit 注入依赖）。`service_type` 传具体类供 mypy/运行期类型校验。
from ghrah.subject.recovery.desired_state import (  # noqa: E402
    DesiredStateStore,
)
from ghrah.subject.recovery.reconciler import (  # noqa: E402
    ReconciliationService,
)

DESIRED_STATE_STORE = SubjectServiceKey[DesiredStateStore](
    "desired_state_store",
    DesiredStateStore,
)
RECONCILIATION_SERVICE = SubjectServiceKey[ReconciliationService](
    "reconciliation_service",
    ReconciliationService,
)
