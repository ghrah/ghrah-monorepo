"""Subject 配置定义。

管理 Subject 的运行时配置，包括工作区路径、数据库路径、权限策略和 Core 连接。

S2.0 配置拆分：把上帝配置对象拆为各 Unit 独立配置切片，`from_env()` 向后兼容。
旧 flat 字段（workspace_root/db_path/manifest_root/hitl_policy/core/log_level）保留为兼容真相，
新 slice（persistence/sandbox/manifest/hitl）由 flat 字段派生或可显式传入。
"""

from __future__ import annotations

import logging
import os
from dataclasses import InitVar, dataclass, field
from pathlib import Path

from ghrah.protocol.types import RecoveryAction

logger = logging.getLogger(__name__)


def _safe_float(value: str, default: float, name: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        logger.warning("Invalid float for %s=%r, using default %s", name, value, default)
        return default


def _safe_int(value: str | None, default: int | None, name: str) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning("Invalid int for %s=%r, using default %s", name, value, default)
        return default


@dataclass
class HITLPolicyConfig:
    """HITL 权限策略配置。

    运行时覆盖层，用于收紧 manifest 声明的权限：
    - auto_approve_abilities：管理员强制放行的能力（覆盖 manifest 的 require_hitl=True）
    - require_approval_by_default：对未在 manifest 中注册的能力的兜底策略
    - allowed_paths：允许访问的路径白名单（用于文件系统权限检查）
    - workspace_root：工作区根路径，此路径下的操作自动放行

    注意：能力的 require_hitl/fs_write/fs_read_only/shell_access 标记
    从 manifest PermissionFlags 中获取，不再在此配置中指定。
    """

    auto_approve_abilities: list[str] = field(default_factory=list)
    require_approval_by_default: bool = True
    allowed_paths: list[str] = field(default_factory=list)
    workspace_root: str | None = None


@dataclass
class CoreTransportConfig:
    """Core 传输层配置（原 CoreConnectionConfig，语义更准：传输层）。

    Subject 通过 WebSocket 连接 Core，接收命令并推送事件。

    Attributes:
        url: Core WebSocket URL，如 "ws://localhost:4111/ws"
        reconnect_interval: 重连间隔（秒）
        max_reconnect_attempts: 最大重连尝试次数，None 表示无限重试
        ping_interval: 心跳间隔（秒）
        command_timeout: 命令执行超时时间（秒）
        cluster_id: Subject 持有的稳定 cluster 标识（MVP 单元素，默认 "default"），
            连接/重连成功后自动发 init_cluster(cluster_id)；不复用 transport 随机 client_id
    """

    url: str = "ws://localhost:4111/ws"
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int | None = None
    ping_interval: float = 30.0
    command_timeout: float = 300.0
    cluster_id: str = "default"


@dataclass
class PersistenceConfig:
    """持久化 Unit 配置切片。

    Attributes:
        db_path: SQLite 数据库文件路径（持久化 ActionChain 和上下文）
    """

    db_path: str = os.path.expanduser("~/.ghrah/subject.db")


@dataclass
class SandboxUnitConfig:
    """sandbox Unit 配置切片。

    注意：区别于 ``SandboxExecutorConfig``（executor 内部：max_output_bytes/blocked_commands
    /env_overrides）。本切片是 sandbox Unit 的装配层配置（workspace_root + default_timeout）。

    Attributes:
        workspace_root: 工作区根路径（Subject 持有的文件系统根目录）
        default_timeout: 默认命令超时（秒），现从 core.command_timeout 拆出独立字段
    """

    workspace_root: str = os.path.expanduser("~/ghrah-workspace")
    default_timeout: float = 300.0


@dataclass
class ManifestConfig:
    """manifest Unit 配置切片。

    Attributes:
        manifest_root: manifest 存储根路径
    """

    manifest_root: str = os.path.expanduser("~/.ghrah/manifests")


# §7.7 transport kind 配置（Stage 2 仅实现 websocket，预留 ipc/grpc）
@dataclass
class TransportKindConfig:
    """transport kind 配置（Stage 2 仅实现 websocket，预留 ipc/grpc/http）。

    Attributes:
        core: core 传输层类型，websocket | ipc | grpc
        observer: observer 传输层类型，websocket | ipc | http | grpc
    """

    core: str = "websocket"
    observer: str = "websocket"


@dataclass
class ProjectConfig:
    """project Unit 配置切片。

    Attributes:
        default_workspace_locator: default project 首启 bootstrap 用的工作区
            locator（git 类型，``file://`` 解析）。空串表示派生自
            ``sandbox.workspace_root + "/projects/default"``（由
            ``SubjectConfig.__post_init__`` 填充）。
        default_db_path_template: per-project 独立 DB 路径模板，``{project_id}``
            占位符由 ProjectManager 替换。
    """

    default_workspace_locator: str = ""
    default_db_path_template: str = "~/.ghrah/projects/{project_id}.db"


@dataclass
class RecoveryConfig:
    """recovery Unit 配置切片。

    Attributes:
        enabled: 是否在 engine.start() 末尾触发 reconcile
        subject_id: 对账归属的 subject 标识（默认 "default"）
        on_unknown_workspace: reconcile 遇到孤立 workspace 时的默认策略
        reconcile_on_start: 启动时是否自动对账（enabled 之外的独立开关）
        bootstrap_default_project: 首启自动建 default project（决策 6）
    """

    enabled: bool = True
    subject_id: str = "default"
    on_unknown_workspace: RecoveryAction = RecoveryAction.PAUSE
    reconcile_on_start: bool = True
    bootstrap_default_project: bool = True


@dataclass
class RoomFilterConfig:
    """Room Filter Unit 配置切片（E1：能力结果 → RoomLog 显式 Filter）。

    白名单配置驱动（用户裁决：零隐式行为——非白名单/无 room 上下文的
    能力结果一律不落 Room；manifest ``chat_visible`` 元数据扩展属 E2）。

    Attributes:
        enabled: 是否挂载 Filter Unit（False = 完全无过滤行为）
        abilities: 白名单能力名（命中且 success 且带 room 上下文才落账）
    """

    enabled: bool = True
    abilities: tuple[str, ...] = ("conversation",)


@dataclass
class SubjectConfig:
    """Subject 运行时配置（各 Unit 配置切片的容器）。

    Subject 是系统的控制面/执行层，持有工作区、执行沙箱命令、
    持久化 ActionChain、裁决 HITL、组装跨 Agent 上下文。

    向后兼容：旧 flat 字段（workspace_root/db_path/manifest_root/hitl_policy/core/log_level）
    仍可被 SubjectConfig(workspace_root=...) 构造。Unit 经 ``config.<slice>`` 读自己那一片；
    ``__post_init__`` 负责在 slice 未显式传入时由 flat 字段派生。

    Slice 字段（persistence/sandbox/manifest/hitl）通过 InitVar 传入，
    读期以只读 property 暴露为非 Optional 类型（mypy strict 友好）。

    Attributes:
        workspace_root: 工作区根路径（Subject 持有的文件系统根目录）
        db_path: SQLite 数据库文件路径（持久化 ActionChain 和上下文）
        manifest_root: manifest 存储根路径
        hitl_policy: HITL 权限策略配置
        core: Core 传输层配置
        log_level: 日志级别
        transport: transport kind 配置（websocket/ipc/grpc）
        enabled_third_party_units: 第三方 Unit allowlist（§7.6）
    """

    # 旧 flat 字段保留，避免破坏 scripts/start_all.py / conftest.py / 外部构造代码。
    workspace_root: str = os.path.expanduser("~/ghrah-workspace")
    db_path: str = os.path.expanduser("~/.ghrah/subject.db")
    manifest_root: str = os.path.expanduser("~/.ghrah/manifests")
    hitl_policy: HITLPolicyConfig = field(default_factory=HITLPolicyConfig)
    core: CoreTransportConfig = field(default_factory=CoreTransportConfig)
    log_level: str = "INFO"

    # slice 显式传入入口（InitVar：不成为实例字段，仅参与 __post_init__）。
    persistence_slice: InitVar[PersistenceConfig | None] = None
    sandbox_slice: InitVar[SandboxUnitConfig | None] = None
    manifest_slice: InitVar[ManifestConfig | None] = None
    hitl_slice: InitVar[HITLPolicyConfig | None] = None
    project_slice: InitVar[ProjectConfig | None] = None
    recovery_slice: InitVar[RecoveryConfig | None] = None
    room_filter_slice: InitVar[RoomFilterConfig | None] = None

    # 非 slice 的新字段（有默认值，可直接构造）。
    transport: TransportKindConfig = field(default_factory=TransportKindConfig)
    enabled_third_party_units: list[str] = field(default_factory=list)

    # private backing（init=False，__post_init__ 后必有值；保证 property 非 Optional）。
    _persistence: PersistenceConfig = field(init=False)
    _sandbox: SandboxUnitConfig = field(init=False)
    _manifest: ManifestConfig = field(init=False)
    _hitl: HITLPolicyConfig = field(init=False)
    _project: ProjectConfig = field(init=False)
    _recovery: RecoveryConfig = field(init=False)
    _room_filter: RoomFilterConfig = field(init=False)

    def __post_init__(
        self,
        persistence_slice: PersistenceConfig | None,
        sandbox_slice: SandboxUnitConfig | None,
        manifest_slice: ManifestConfig | None,
        hitl_slice: HITLPolicyConfig | None,
        project_slice: ProjectConfig | None,
        recovery_slice: RecoveryConfig | None,
        room_filter_slice: RoomFilterConfig | None,
    ) -> None:
        self._persistence = persistence_slice or PersistenceConfig(db_path=self.db_path)
        self._sandbox = sandbox_slice or SandboxUnitConfig(
            workspace_root=self.workspace_root,
            default_timeout=self.core.command_timeout,
        )
        self._manifest = manifest_slice or ManifestConfig(manifest_root=self.manifest_root)
        self._hitl = hitl_slice or self.hitl_policy
        # project slice：default_workspace_locator 为空时派生自 sandbox.workspace_root
        # + "/projects/default"（flat 兼容真相）。
        self._project = project_slice or ProjectConfig(
            default_workspace_locator=(
                ""
                if not self._sandbox.workspace_root
                else self._sandbox.workspace_root.rstrip("/") + "/projects/default"
            ),
        )
        self._recovery = recovery_slice or RecoveryConfig()
        self._room_filter = room_filter_slice or RoomFilterConfig()

    # ── 只读 slice property（非 Optional，mypy strict 友好）──

    @property
    def persistence(self) -> PersistenceConfig:
        return self._persistence

    @property
    def core_db_path(self) -> str:
        """Core agent 链 sqlite 路径（聚合裁决 D-C：真相源在 Core 内建 backend）。

        与 subject 自身 db 同目录独立文件（``ghrah.db``）。registry 构造
        CoreUnit 的 persistence_factory 与 ledger 读侧投影共用本派生，
        保证读写同一文件。
        """
        return str(Path(self._persistence.db_path).parent / "ghrah.db")

    @property
    def sandbox(self) -> SandboxUnitConfig:
        return self._sandbox

    @property
    def manifest(self) -> ManifestConfig:
        return self._manifest

    @property
    def hitl(self) -> HITLPolicyConfig:
        return self._hitl

    @property
    def project(self) -> ProjectConfig:
        return self._project

    @property
    def recovery(self) -> RecoveryConfig:
        return self._recovery

    @property
    def room_filter(self) -> RoomFilterConfig:
        return self._room_filter

    @classmethod
    def from_env(cls) -> SubjectConfig:
        """从环境变量创建配置。

        环境变量命名规则：GHRAH_SUBJECT_<大写属性名>
        例如：GHRAH_SUBJECT_WORKSPACE_ROOT, GHRAH_SUBJECT_DB_PATH

        嵌套配置使用双下划线分隔：
        例如：GHRAH_SUBJECT_CORE_URL, GHRAH_SUBJECT_HITL_POLICY_WORKSPACE_ROOT

        - GHRAH_SUBJECT_SANDBOX_DEFAULT_TIMEOUT（回退 GHRAH_SUBJECT_CORE_COMMAND_TIMEOUT）
        - GHRAH_SUBJECT_ABILITY_HITL_TIMEOUT（回退 GHRAH_SUBJECT_CORE_COMMAND_TIMEOUT）
        - GHRAH_SUBJECT_TRANSPORT_CORE_KIND / GHRAH_SUBJECT_TRANSPORT_OBSERVER_KIND
        - GHRAH_SUBJECT_ENABLED_UNITS（逗号分隔，第三方 Unit allowlist）
        - GHRAH_SUBJECT_PROJECT_DEFAULT_WORKSPACE_LOCATOR
          （空→派生自 sandbox.workspace_root + "/projects/default"）
        - GHRAH_SUBJECT_PROJECT_DEFAULT_DB_PATH_TEMPLATE
        - GHRAH_SUBJECT_RECOVERY_ENABLED
        - GHRAH_SUBJECT_RECOVERY_SUBJECT_ID
        - GHRAH_SUBJECT_RECOVERY_ON_UNKNOWN_WORKSPACE（resume|pause|drop）
        - GHRAH_SUBJECT_RECOVERY_RECONCILE_ON_START
        - GHRAH_SUBJECT_RECOVERY_BOOTSTRAP_DEFAULT_PROJECT
        - GHRAH_SUBJECT_ROOM_FILTER_ENABLED
        - GHRAH_SUBJECT_ROOM_FILTER_ABILITIES（逗号分隔白名单能力名）
        """
        hitl_policy = HITLPolicyConfig(
            auto_approve_abilities=os.environ.get(
                "GHRAH_SUBJECT_HITL_AUTO_APPROVE_ABILITIES", ""
            ).split(",")
            if os.environ.get("GHRAH_SUBJECT_HITL_AUTO_APPROVE_ABILITIES")
            else [],
            require_approval_by_default=os.environ.get(
                "GHRAH_SUBJECT_HITL_REQUIRE_APPROVAL", "true"
            ).lower()
            in ("true", "1", "yes"),
            allowed_paths=os.environ.get("GHRAH_SUBJECT_HITL_ALLOWED_PATHS", "").split(";")
            if os.environ.get("GHRAH_SUBJECT_HITL_ALLOWED_PATHS")
            else [],
            workspace_root=os.environ.get("GHRAH_SUBJECT_HITL_WORKSPACE_ROOT"),
        )

        core = CoreTransportConfig(
            url=os.environ.get("GHRAH_SUBJECT_CORE_URL", "ws://localhost:4111/ws"),
            reconnect_interval=_safe_float(
                os.environ.get("GHRAH_SUBJECT_CORE_RECONNECT_INTERVAL", "5.0"),
                5.0,
                "GHRAH_SUBJECT_CORE_RECONNECT_INTERVAL",
            ),
            ping_interval=_safe_float(
                os.environ.get("GHRAH_SUBJECT_CORE_PING_INTERVAL", "30.0"),
                30.0,
                "GHRAH_SUBJECT_CORE_PING_INTERVAL",
            ),
            command_timeout=_safe_float(
                os.environ.get("GHRAH_SUBJECT_CORE_COMMAND_TIMEOUT", "300.0"),
                300.0,
                "GHRAH_SUBJECT_CORE_COMMAND_TIMEOUT",
            ),
            max_reconnect_attempts=_safe_int(
                os.environ.get("GHRAH_SUBJECT_CORE_MAX_RECONNECT_ATTEMPTS"),
                None,
                "GHRAH_SUBJECT_CORE_MAX_RECONNECT_ATTEMPTS",
            ),
            cluster_id=os.environ.get("GHRAH_SUBJECT_CORE_CLUSTER_ID", "default"),
        )

        # sandbox default_timeout：专用 env，未设置时回退到 core.command_timeout（向后兼容）
        sandbox_default_timeout_env = os.environ.get("GHRAH_SUBJECT_SANDBOX_DEFAULT_TIMEOUT")
        if sandbox_default_timeout_env:
            sandbox_default_timeout = _safe_float(
                sandbox_default_timeout_env,
                core.command_timeout,
                "GHRAH_SUBJECT_SANDBOX_DEFAULT_TIMEOUT",
            )
        else:
            sandbox_default_timeout = core.command_timeout

        transport = TransportKindConfig(
            core=os.environ.get("GHRAH_SUBJECT_TRANSPORT_CORE_KIND", "websocket"),
            observer=os.environ.get("GHRAH_SUBJECT_TRANSPORT_OBSERVER_KIND", "websocket"),
        )

        enabled_third_party_units = [
            u.strip()
            for u in os.environ.get("GHRAH_SUBJECT_ENABLED_UNITS", "").split(",")
            if u.strip()
        ]

        workspace_root = os.environ.get(
            "GHRAH_SUBJECT_WORKSPACE_ROOT", os.path.expanduser("~/ghrah-workspace")
        )

        # project slice：default_workspace_locator 空时由 __post_init__ 派生。
        project_default_workspace_locator = os.environ.get(
            "GHRAH_SUBJECT_PROJECT_DEFAULT_WORKSPACE_LOCATOR", ""
        )
        project_default_db_path_template = os.environ.get(
            "GHRAH_SUBJECT_PROJECT_DEFAULT_DB_PATH_TEMPLATE",
            "~/.ghrah/projects/{project_id}.db",
        )
        project_slice = ProjectConfig(
            default_workspace_locator=project_default_workspace_locator,
            default_db_path_template=project_default_db_path_template,
        )

        # recovery slice
        _on_unknown_raw = os.environ.get(
            "GHRAH_SUBJECT_RECOVERY_ON_UNKNOWN_WORKSPACE", "pause"
        ).lower()
        try:
            on_unknown_workspace = RecoveryAction(_on_unknown_raw)
        except ValueError:
            logger.warning(
                "Invalid RecoveryAction for "
                "GHRAH_SUBJECT_RECOVERY_ON_UNKNOWN_WORKSPACE=%r, using default PAUSE",
                _on_unknown_raw,
            )
            on_unknown_workspace = RecoveryAction.PAUSE
        recovery_slice = RecoveryConfig(
            enabled=os.environ.get("GHRAH_SUBJECT_RECOVERY_ENABLED", "true").lower()
            in ("true", "1", "yes"),
            subject_id=os.environ.get("GHRAH_SUBJECT_RECOVERY_SUBJECT_ID", "default"),
            on_unknown_workspace=on_unknown_workspace,
            reconcile_on_start=os.environ.get(
                "GHRAH_SUBJECT_RECOVERY_RECONCILE_ON_START", "true"
            ).lower()
            in ("true", "1", "yes"),
            bootstrap_default_project=os.environ.get(
                "GHRAH_SUBJECT_RECOVERY_BOOTSTRAP_DEFAULT_PROJECT", "true"
            ).lower()
            in ("true", "1", "yes"),
        )

        # room_filter slice
        room_filter_slice = RoomFilterConfig(
            enabled=os.environ.get("GHRAH_SUBJECT_ROOM_FILTER_ENABLED", "true").lower()
            in ("true", "1", "yes"),
            abilities=tuple(
                a.strip()
                for a in os.environ.get(
                    "GHRAH_SUBJECT_ROOM_FILTER_ABILITIES", "conversation"
                ).split(",")
                if a.strip()
            ),
        )

        return cls(
            workspace_root=workspace_root,
            db_path=os.environ.get(
                "GHRAH_SUBJECT_DB_PATH", os.path.expanduser("~/.ghrah/subject.db")
            ),
            manifest_root=os.environ.get(
                "GHRAH_SUBJECT_MANIFEST_ROOT", os.path.expanduser("~/.ghrah/manifests")
            ),
            hitl_policy=hitl_policy,
            core=core,
            log_level=os.environ.get("GHRAH_SUBJECT_LOG_LEVEL", "INFO"),
            # slice 显式传入（保证 env 优先级；persistence/manifest/hitl 由 flat 派生）
            sandbox_slice=SandboxUnitConfig(
                workspace_root=workspace_root,
                default_timeout=sandbox_default_timeout,
            ),
            transport=transport,
            enabled_third_party_units=enabled_third_party_units,
            project_slice=project_slice,
            recovery_slice=recovery_slice,
            room_filter_slice=room_filter_slice,
        )


# 别名兼容：CoreConnectionConfig → CoreTransportConfig（改名，保留旧名供外部引用）
CoreConnectionConfig = CoreTransportConfig
