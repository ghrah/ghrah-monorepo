# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Typed service keys and runtime service contracts for Subject units."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from ghrah.manifest.types import PermissionFlags  # type: ignore[import-untyped]
from ghrah.subject.hitl.notary import HITLNotary
from ghrah.subject.manifest_store.store import ManifestStore
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.transport.core import CoreTransport
from ghrah.subject.transport.observer import ObserverEndpoint

__all__ = [
    "ABILITY_EXECUTOR",
    "CAPABILITY_REGISTRY",
    "COMMAND_BRIDGE",
    "COMMAND_RUNNER",
    "CORE_TRANSPORT",
    "EVENT_BRIDGE",
    "HITL_NOTARY",
    "MANIFEST_PERMISSION_INDEX",
    "MANIFEST_STORE",
    "MCP_CLIENT_REGISTRY",
    "OBSERVER_ENDPOINT",
    "OBSERVER_EVENT_BUS",
    "PERMISSION_SERVICE",
    "SANDBOX_EXECUTOR",
    "SESSION_REGISTRY",
    "WORKSPACE_SERVICE",
    "AbilityExecutor",
    "CommandRunner",
    "ManifestPermissionIndex",
    "ObserverEventBus",
    "PermissionService",
    "SubjectServiceKey",
    "WorkspaceService",
]

T = TypeVar("T")


@dataclass(frozen=True)
class SubjectServiceKey(Generic[T]):
    """Typed key for values stored in :class:`SubjectServices`."""

    name: str
    service_type: type[Any] | tuple[type[Any], ...] = object


class WorkspaceService(Protocol):
    """Workspace contract required by runtime units."""

    @property
    def root_path(self) -> str:
        """Return the workspace root path."""

    async def create_workspace(self, agent_name: str) -> Any:
        """Create or return a workspace for an agent."""

    def resolve_agent_path(self, agent_name: str) -> str | None:
        """Resolve an agent name to its workspace path, if present."""


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


class ObserverEventBus(Protocol):
    """Observer-facing event bridge contract."""

    async def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        """Publish an event to observer sessions."""

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        """Subscribe an observer session."""


class _ReservedService(Protocol):
    """Placeholder protocol for services planned after Stage 2."""


WORKSPACE_SERVICE = SubjectServiceKey[WorkspaceService]("workspace_service")
COMMAND_RUNNER = SubjectServiceKey[CommandRunner]("command_runner")
SANDBOX_EXECUTOR = SubjectServiceKey[SandboxExecutor]("sandbox_executor", SandboxExecutor)
MANIFEST_STORE = SubjectServiceKey[ManifestStore]("manifest_store", ManifestStore)
MANIFEST_PERMISSION_INDEX = SubjectServiceKey[ManifestPermissionIndex](
    "manifest_permission_index"
)
PERMISSION_SERVICE = SubjectServiceKey[PermissionService]("permission_service")
HITL_NOTARY = SubjectServiceKey[HITLNotary]("hitl_notary", HITLNotary)
CORE_TRANSPORT = SubjectServiceKey[CoreTransport]("core_transport")
OBSERVER_ENDPOINT = SubjectServiceKey[ObserverEndpoint]("observer_endpoint")
OBSERVER_EVENT_BUS = SubjectServiceKey[ObserverEventBus]("observer_event_bus")
CAPABILITY_REGISTRY = SubjectServiceKey[CapabilityRegistry](
    "capability_registry",
    CapabilityRegistry,
)
ABILITY_EXECUTOR = SubjectServiceKey[AbilityExecutor]("ability_executor")

# Reserved for Stage 3+ integrations. The keys are intentionally real so
# dependency declarations can be written before the concrete services exist.
MCP_CLIENT_REGISTRY = SubjectServiceKey[_ReservedService]("mcp_client_registry")
SESSION_REGISTRY = SubjectServiceKey[_ReservedService]("session_registry")
COMMAND_BRIDGE = SubjectServiceKey[Callable[..., Awaitable[Any]]]("command_bridge")
EVENT_BRIDGE = SubjectServiceKey[Callable[..., Awaitable[Any]]]("event_bridge")
