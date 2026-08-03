# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Subject runtime infrastructure."""

from ghrah.subject.runtime.capability import (
    AbilityContribution,
    CapabilityProvider,
    CapabilityRegistry,
    PermissionDescriptor,
)
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.dependency import topological_sort
from ghrah.subject.runtime.dispatcher import CommandRoute, MessageDispatcher
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import (
    ABILITY_EXECUTOR,
    CAPABILITY_REGISTRY,
    COMMAND_BRIDGE,
    COMMAND_RUNNER,
    EVENT_BRIDGE,
    HITL_NOTARY,
    HITL_POLICY,
    LEDGER,
    MANIFEST_PERMISSION_INDEX,
    MANIFEST_STORE,
    MCP_CLIENT_REGISTRY,
    OBSERVER_ENDPOINT,
    OBSERVER_EVENT_BUS,
    PERMISSION_SERVICE,
    PERSISTENCE,
    SANDBOX_EXECUTOR,
    SESSION_REGISTRY,
    WORKSPACE_SERVICE,
    AbilityExecutor,
    CommandRunner,
    ManifestPermissionIndex,
    ObserverEventBus,
    PermissionService,
    SubjectServiceKey,
    WorkspaceService,
)
from ghrah.subject.runtime.services import SubjectServices

__all__ = [
    "ABILITY_EXECUTOR",
    "CAPABILITY_REGISTRY",
    "COMMAND_BRIDGE",
    "COMMAND_RUNNER",
    "EVENT_BRIDGE",
    "HITL_NOTARY",
    "HITL_POLICY",
    "LEDGER",
    "MANIFEST_PERMISSION_INDEX",
    "MANIFEST_STORE",
    "MCP_CLIENT_REGISTRY",
    "OBSERVER_ENDPOINT",
    "OBSERVER_EVENT_BUS",
    "PERMISSION_SERVICE",
    "PERSISTENCE",
    "SANDBOX_EXECUTOR",
    "SESSION_REGISTRY",
    "WORKSPACE_SERVICE",
    "AbilityContribution",
    "AbilityExecutor",
    "CapabilityProvider",
    "CapabilityRegistry",
    "CommandRoute",
    "CommandRunner",
    "ManifestPermissionIndex",
    "MessageDispatcher",
    "ObserverEventBus",
    "PermissionDescriptor",
    "PermissionService",
    "SubjectContext",
    "SubjectEngine",
    "SubjectServiceKey",
    "SubjectServices",
    "WorkspaceService",
    "topological_sort",
]
