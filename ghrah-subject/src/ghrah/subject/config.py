"""Subject 配置定义。

管理 Subject 的运行时配置，包括工作区路径、数据库路径、权限策略和 Gateway 连接。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

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
class GatewayConnectionConfig:
    """Gateway 连接配置。

    Subject 通过 WebSocket 连接 Gateway，接收命令并推送事件。

    Attributes:
        url: Gateway WebSocket URL，如 "ws://localhost:4111/ws"
        reconnect_interval: 重连间隔（秒）
        max_reconnect_attempts: 最大重连尝试次数，None 表示无限重试
        ping_interval: 心跳间隔（秒）
        command_timeout: 命令执行超时时间（秒）
    """

    url: str = "ws://localhost:4111/ws"
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int | None = None
    ping_interval: float = 30.0
    command_timeout: float = 300.0


@dataclass
class SubjectConfig:
    """Subject 运行时配置。

    Subject 是系统的控制面/执行层，持有工作区、执行沙箱命令、
    持久化 ActionChain、裁决 HITL、组装跨 Agent 上下文。

    Attributes:
        workspace_root: 工作区根路径（Subject 持有的文件系统根目录）
        db_path: SQLite 数据库文件路径（持久化 ActionChain 和上下文）
        hitl_policy: HITL 权限策略配置
        gateway: Gateway 连接配置
        log_level: 日志级别
    """

    workspace_root: str = os.path.expanduser("~/ghrah-workspace")
    db_path: str = os.path.expanduser("~/.ghrah/subject.db")
    manifest_root: str = os.path.expanduser("~/.ghrah/manifests")
    hitl_policy: HITLPolicyConfig = field(default_factory=HITLPolicyConfig)
    gateway: GatewayConnectionConfig = field(default_factory=GatewayConnectionConfig)
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> SubjectConfig:
        """从环境变量创建配置。

        环境变量命名规则：GHRAH_SUBJECT_<大写属性名>
        例如：GHRAH_SUBJECT_WORKSPACE_ROOT, GHRAH_SUBJECT_DB_PATH

        嵌套配置使用双下划线分隔：
        例如：GHRAH_SUBJECT_GATEWAY_URL, GHRAH_SUBJECT_HITL_POLICY_WORKSPACE_ROOT
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
            allowed_paths=os.environ.get(
                "GHRAH_SUBJECT_HITL_ALLOWED_PATHS", ""
            ).split(";")
            if os.environ.get("GHRAH_SUBJECT_HITL_ALLOWED_PATHS")
            else [],
            workspace_root=os.environ.get("GHRAH_SUBJECT_HITL_WORKSPACE_ROOT"),
        )

        gateway = GatewayConnectionConfig(
            url=os.environ.get("GHRAH_SUBJECT_GATEWAY_URL", "ws://localhost:4111/ws"),
            reconnect_interval=_safe_float(
                os.environ.get("GHRAH_SUBJECT_GATEWAY_RECONNECT_INTERVAL", "5.0"),
                5.0,
                "GHRAH_SUBJECT_GATEWAY_RECONNECT_INTERVAL",
            ),
            ping_interval=_safe_float(
                os.environ.get("GHRAH_SUBJECT_GATEWAY_PING_INTERVAL", "30.0"),
                30.0,
                "GHRAH_SUBJECT_GATEWAY_PING_INTERVAL",
            ),
            command_timeout=_safe_float(
                os.environ.get("GHRAH_SUBJECT_GATEWAY_COMMAND_TIMEOUT", "300.0"),
                300.0,
                "GHRAH_SUBJECT_GATEWAY_COMMAND_TIMEOUT",
            ),
        )

        max_attempts_str = os.environ.get("GHRAH_SUBJECT_GATEWAY_MAX_RECONNECT_ATTEMPTS")
        gateway.max_reconnect_attempts = _safe_int(
            max_attempts_str, None, "GHRAH_SUBJECT_GATEWAY_MAX_RECONNECT_ATTEMPTS"
        )

        return cls(
            workspace_root=os.environ.get(
                "GHRAH_SUBJECT_WORKSPACE_ROOT", os.path.expanduser("~/ghrah-workspace")
            ),
            db_path=os.environ.get(
                "GHRAH_SUBJECT_DB_PATH", os.path.expanduser("~/.ghrah/subject.db")
            ),
            manifest_root=os.environ.get(
                "GHRAH_SUBJECT_MANIFEST_ROOT", os.path.expanduser("~/.ghrah/manifests")
            ),
            hitl_policy=hitl_policy,
            gateway=gateway,
            log_level=os.environ.get("GHRAH_SUBJECT_LOG_LEVEL", "INFO"),
        )
