"""FastAPI 应用入口（S2.3 后降级为薄 facade）。

Observer FastAPI app 由 ``WebSocketObserverEndpointUnit`` 在
``engine.start()`` 期间创建并持有（amendment A6：Unit owns app）。
``create_app(config, *, engine)`` 仅作为取回该 app 的薄 facade，
不再自建 ConnectionManager/EventBus/ObserverRouter/FastAPI。

生命周期：先 ``await engine.start()``（Unit 初始化并构造 app），
再 ``create_app(..., engine=engine)`` 取回 app，最后 ``await engine.stop()``。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI

from ghrah.subject.server.config import ObserverServerConfig

if TYPE_CHECKING:
    from ghrah.subject.runtime.engine import SubjectEngine

logger = logging.getLogger(__name__)


def create_app(
    config: ObserverServerConfig | None = None,
    *,
    engine: SubjectEngine,
) -> FastAPI:
    """返回 engine 持有的 Observer FastAPI app（Unit owns app, amendment A6）。

    Args:
        config: 保留用于签名兼容/未来校验；Unit 的 ws_path/event_replay_capacity
            已在 ``engine.start() -> WebSocketObserverEndpointUnit.init()`` 时由
            该 Unit 自身的 ObserverServerConfig 确定，facade 不重新配置已初始化 Unit。
            若需覆盖这些字段，必须在注册/构造 Unit 阶段提前传入，而非在此事后覆盖。
        engine: 已 start 的 SubjectEngine（必须已注册 websocket_observer_endpoint Unit）。

    Returns:
        WebSocketObserverEndpointUnit 持有的 FastAPI 实例。

    Raises:
        RuntimeError: engine 未 start 或未注册 websocket_observer_endpoint Unit。
    """
    del config
    from ghrah.subject.units.websocket_observer_endpoint import (
        WebSocketObserverEndpointUnit,
    )

    unit = engine.get_unit("websocket_observer_endpoint")
    if not isinstance(unit, WebSocketObserverEndpointUnit):
        raise RuntimeError(
            "create_app requires a started engine with the websocket_observer_endpoint "
            "unit (register_builtin_units(profile='full') + engine.start())."
        )
    return unit.app


async def serve() -> None:
    """启动 Subject Observer 服务器（engine 生命周期 + uvicorn）。"""
    import uvicorn

    observer_config = ObserverServerConfig.from_env()
    engine = _build_engine()
    await engine.start()
    try:
        app = create_app(observer_config, engine=engine)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=observer_config.host,
                port=observer_config.port,
                log_level=observer_config.log_level.lower(),
                ws_ping_interval=observer_config.ping_interval,
                ws_ping_timeout=observer_config.ping_timeout,
            )
        )
        await server.serve()
    finally:
        await engine.stop()


def _build_engine() -> SubjectEngine:
    from ghrah.subject.config import SubjectConfig
    from ghrah.subject.runtime.engine import SubjectEngine

    config = SubjectConfig.from_env()
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="full")
    engine.discover()
    engine.enable_from_config()
    engine.validate()
    return engine


def main() -> None:
    """启动 Observer 服务器。"""
    import asyncio

    from ghrah.subject.config import SubjectConfig

    config = SubjectConfig.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("ghrah-subject observer server starting (engine, profile=full)...")
    asyncio.run(serve())


if __name__ == "__main__":
    main()
