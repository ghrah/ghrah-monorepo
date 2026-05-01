"""Subject Observer Server 包。

提供 Observer WebSocket 服务器，让 Observer 通过 WebSocket 连接到 Subject，
接收事件和发送命令。

核心组件：
    - ObserverServerConfig: 服务器配置
    - ConnectionManager: Observer 连接管理
    - EventBus: 事件发布与重放
    - ObserverRouter: 命令路由（通过回调与 SubjectService 解耦）
    - ObserverServer: WebSocket 连接处理器
    - create_app: FastAPI 应用工厂
"""

from ghrah.subject.server.app import create_app
from ghrah.subject.server.config import ObserverServerConfig
from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus, EventStore
from ghrah.subject.server.router import CoreForwardHandler, ObserverRouter
from ghrah.subject.server.server import ObserverServer

__all__ = [
    "ConnectionManager",
    "CoreForwardHandler",
    "EventBus",
    "EventStore",
    "ObserverRouter",
    "ObserverServer",
    "ObserverServerConfig",
    "create_app",
]
