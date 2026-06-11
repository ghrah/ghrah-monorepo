"""FastAPI 应用入口。

创建 FastAPI 实例，管理应用生命周期，
注册 Observer WebSocket 路由和配置中间件。

Subject 的 Observer Server 职责：
    - 接受 Observer 的 WebSocket 连接
    - 路由 Observer 命令到本地处理器或转发到 Core
    - 将 Core 事件和 HITL 请求推送给 Observer
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket

from ghrah.protocol.types import Message
from ghrah.subject.server.config import ObserverServerConfig
from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus
from ghrah.subject.server.router import CommandHandler, CoreForwardHandler, ObserverRouter
from ghrah.subject.server.server import ObserverServer

logger = logging.getLogger(__name__)


def create_app(
    config: ObserverServerConfig | None = None,
    *,
    core_forward_handler: CoreForwardHandler | None = None,
    workspace_handler: CommandHandler | None = None,
    manifest_handler: CommandHandler | None = None,
    hitl_response_handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    persist_handler: CommandHandler | None = None,
    ability_handler: CommandHandler | None = None,
    chain_history_handler: CommandHandler | None = None,
    core_event_handler: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
) -> FastAPI:
    """创建 FastAPI 应用实例。

    Args:
        config: Observer Server 配置，None 时使用默认配置
        core_forward_handler: Agent 管理命令转发到 Core 的回调
        workspace_handler: workspace_* 命令的本地处理器回调
        manifest_handler: manifest_* 命令的本地处理器回调
        hitl_response_handler: HITL 响应本地处理器回调
        persist_handler: persist_* 命令的本地处理器回调
        ability_handler: execute_ability 命令的本地处理器回调
        chain_history_handler: get_chain_history 命令的本地处理器回调
        core_event_handler: Core 事件转发回调（如未提供，自动通过 EventBus 转发）

    Returns:
        配置好的 FastAPI 应用实例
    """
    if config is None:
        config = ObserverServerConfig()

    connection_manager = ConnectionManager()
    event_bus = EventBus(
        connection_manager,
        event_store_capacity=config.event_replay_capacity,
    )

    effective_core_event_handler = core_event_handler

    async def _default_core_event_handler(event_type: str, payload: dict[str, Any]) -> None:
        message = Message(type=event_type, payload=payload)
        await event_bus.emit_core_event(message)

    if effective_core_event_handler is None:
        effective_core_event_handler = _default_core_event_handler
    router = ObserverRouter(
        connection_manager,
        event_bus,
        core_forward_handler=core_forward_handler,
        workspace_handler=workspace_handler,
        manifest_handler=manifest_handler,
        hitl_response_handler=hitl_response_handler,
        persist_handler=persist_handler,
        ability_handler=ability_handler,
        chain_history_handler=chain_history_handler,
    )
    ws_server = ObserverServer(config, connection_manager, router, event_bus)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logger.info("Starting ghrah-subject observer server...")
        await event_bus.start()
        yield
        logger.info("Shutting down ghrah-subject observer server...")
        await event_bus.stop()
        logger.info("Observer server shutdown complete")

    app = FastAPI(
        title="ghrah-subject-observer",
        description="ghrah-subject Observer WebSocket server",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.core_event_handler = effective_core_event_handler

    @app.websocket(config.ws_path)
    async def websocket_endpoint(websocket: WebSocket):
        await ws_server.handle_connection(websocket)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "active_sessions": connection_manager.connection_count,
        }

    @app.get("/")
    async def root():
        return {
            "name": "ghrah-subject-observer",
            "version": "0.1.0",
            "description": "ghrah-subject Observer WebSocket server",
        }

    return app


def main() -> None:
    """启动 Observer 服务器。"""
    import uvicorn

    config = ObserverServerConfig.from_env()
    app = create_app(config)

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        ws_ping_interval=config.ping_interval,
        ws_ping_timeout=config.ping_timeout,
    )


if __name__ == "__main__":
    main()
