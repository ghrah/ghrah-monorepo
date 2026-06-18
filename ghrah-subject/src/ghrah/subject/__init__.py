"""ghrah-subject: 控制面/执行层

Subject 是 Core 和 Observer 之间的中间层，所有 Core↔Observer 通信都经过 Subject。
在分布式模式下，Subject 端执行 Ability 并处理 HITL 裁决。
"""

from ghrah.subject.ability_runner import AbilityRunner, AbilityRunnerConfig
from ghrah.subject.config import (
    CoreConnectionConfig,
    CoreTransportConfig,
    HITLPolicyConfig,
    ManifestConfig,
    PersistenceConfig,
    SandboxUnitConfig,
    SubjectConfig,
    TransportKindConfig,
)
from ghrah.subject.hitl import HITLNotary, HITLPolicy, HITLPromise, HITLVerdict
from ghrah.subject.ledger import (
    ActionChainLedger,
    ChainMeta,
    DAGEntry,
    LedgerNode,
    PersistenceError,
)
from ghrah.subject.manifest_store import ManifestStore
from ghrah.subject.permission_checker import (
    PermissionChecker,
    PermissionDecision,
    PermissionVerdict,
)
from ghrah.subject.sandbox import (
    AgentWorkspace,
    CommandResult,
    SandboxExecutor,
    SandboxExecutorConfig,
    SnapshotError,
    SnapshotInfo,
    WorkspaceManager,
    WorkspaceStatus,
)
from ghrah.subject.service import SubjectService

__all__ = [
    "AbilityRunner",
    "AbilityRunnerConfig",
    "ActionChainLedger",
    "AgentWorkspace",
    "ChainMeta",
    "CommandResult",
    "CoreConnectionConfig",
    "CoreTransportConfig",
    "DAGEntry",
    "HITLPolicyConfig",
    "LedgerNode",
    "ManifestConfig",
    "ManifestStore",
    "PersistenceConfig",
    "PersistenceError",
    "PermissionChecker",
    "PermissionDecision",
    "PermissionVerdict",
    "SandboxExecutor",
    "SandboxExecutorConfig",
    "SandboxUnitConfig",
    "SnapshotError",
    "SnapshotInfo",
    "SubjectConfig",
    "TransportKindConfig",
    "HITLNotary",
    "HITLPolicy",
    "HITLPromise",
    "HITLVerdict",
    "SubjectService",
    "WorkspaceManager",
    "WorkspaceStatus",
]
