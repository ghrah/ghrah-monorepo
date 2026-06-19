"""ghrah-subject: 控制面/执行层。

Subject 是 Core 和 Observer 之间的中间层（Agent Effect Host）。
运行时由 SubjectEngine 装配
（register_builtin_units -> discover -> enable_from_config -> validate
-> start -> run_forever -> stop）。
"""

# —— runtime 契约
# —— 各子系统类（保留导出供单测）——
from ghrah.subject.ability_runner import AbilityRunner, AbilityRunnerConfig

# —— SubjectConfig（含 enabled_third_party_units allowlist）——
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
from ghrah.subject.runtime.capability import CapabilityProvider, CapabilityRegistry
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import SubjectServiceKey
from ghrah.subject.runtime.services import SubjectServices
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
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta

__all__ = [
    # runtime 契约
    "SubjectEngine",
    "SubjectUnit",
    "UnitMeta",
    "RouteSpec",
    "SubjectContext",
    "SubjectServices",
    "SubjectServiceKey",
    "CapabilityProvider",
    "CapabilityRegistry",
    # config
    "SubjectConfig",
    "CoreConnectionConfig",
    "CoreTransportConfig",
    "HITLPolicyConfig",
    "ManifestConfig",
    "PersistenceConfig",
    "SandboxUnitConfig",
    "TransportKindConfig",
    # 子系统（单测用）
    "AbilityRunner",
    "AbilityRunnerConfig",
    "ActionChainLedger",
    "AgentWorkspace",
    "ChainMeta",
    "CommandResult",
    "DAGEntry",
    "HITLNotary",
    "HITLPolicy",
    "HITLPromise",
    "HITLVerdict",
    "LedgerNode",
    "ManifestStore",
    "PersistenceError",
    "PermissionChecker",
    "PermissionDecision",
    "PermissionVerdict",
    "SandboxExecutor",
    "SandboxExecutorConfig",
    "SnapshotError",
    "SnapshotInfo",
    "WorkspaceManager",
    "WorkspaceStatus",
]
