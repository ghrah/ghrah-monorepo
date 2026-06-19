# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WebSocket Observer endpoint built-in Subject unit."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, WebSocket

from ghrah.protocol.types import EventType, Message  # type: ignore[import-untyped]
from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import (
    SUBJECT_CORE_EVENT_RECEIVED,
    SUBJECT_HITL_REQUEST_CREATED,
)
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import OBSERVER_ENDPOINT, OBSERVER_EVENT_BUS
from ghrah.subject.server.config import ObserverServerConfig
from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus
from ghrah.subject.server.router import ObserverRouter
from ghrah.subject.server.server import ObserverServer
from ghrah.subject.transport.observer import ObserverCommandHandler
from ghrah.subject.unit.base import SubjectUnit, UnitMeta

__all__ = ["WebSocketObserverEndpointUnit"]

logger = logging.getLogger(__name__)


class _ObserverEventBusAdapter:
    """Service adapter exposing the Observer event bus as a typed bridge."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def publish(self, event_type: str, payload: dict[str, Any]) -> int:
        return await self._event_bus.emit_core_event(
            Message(type=event_type, payload=payload)
        )

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        return self._event_bus.subscribe(*args, **kwargs)


class WebSocketObserverEndpointUnit(SubjectUnit):
    """Composes the Observer WebSocket server components."""

    def __init__(
        self,
        config: SubjectConfig,
        observer_config: ObserverServerConfig | None = None,
    ) -> None:
        self._config = config
        self._observer_config = observer_config
        self._connection_manager: ConnectionManager | None = None
        self._observer_event_bus: EventBus | None = None
        self._observer_event_bus_adapter: _ObserverEventBusAdapter | None = None
        self._router: ObserverRouter | None = None
        self._server: ObserverServer | None = None
        self._app: FastAPI | None = None
        self._meta = UnitMeta(
            name="websocket_observer_endpoint",
            provides=frozenset({OBSERVER_ENDPOINT, OBSERVER_EVENT_BUS}),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def app(self) -> FastAPI:
        if self._app is None:
            raise RuntimeError("WebSocketObserverEndpointUnit has not been initialized.")
        return self._app

    @property
    def connection_manager(self) -> ConnectionManager:
        if self._connection_manager is None:
            raise RuntimeError("WebSocketObserverEndpointUnit has not been initialized.")
        return self._connection_manager

    @property
    def observer_event_bus(self) -> EventBus:
        if self._observer_event_bus is None:
            raise RuntimeError("WebSocketObserverEndpointUnit has not been initialized.")
        return self._observer_event_bus

    @property
    def router(self) -> ObserverRouter:
        if self._router is None:
            raise RuntimeError("WebSocketObserverEndpointUnit has not been initialized.")
        return self._router

    async def init(self, ctx: SubjectContext) -> None:
        config = self._observer_config or ObserverServerConfig(log_level=ctx.config.log_level)
        connection_manager = ConnectionManager()
        observer_event_bus = EventBus(
            connection_manager,
            event_store_capacity=config.event_replay_capacity,
        )
        router = ObserverRouter(
            connection_manager,
            observer_event_bus,
            engine=ctx.engine,
        )
        server = ObserverServer(config, connection_manager, router, observer_event_bus)

        self._connection_manager = connection_manager
        self._observer_event_bus = observer_event_bus
        self._observer_event_bus_adapter = _ObserverEventBusAdapter(observer_event_bus)
        self._router = router
        self._server = server
        self._app = _create_observer_app(config, server, connection_manager)

        ctx.services.set(OBSERVER_ENDPOINT, self)
        ctx.services.set(OBSERVER_EVENT_BUS, self._observer_event_bus_adapter)
        ctx.event_bus.subscribe(SUBJECT_CORE_EVENT_RECEIVED, self._forward_core_event)
        ctx.event_bus.subscribe(SUBJECT_HITL_REQUEST_CREATED, self._forward_hitl_request)

    async def start(
        self,
        on_command: ObserverCommandHandler | None = None,
    ) -> None:
        """Start the Observer event bus.

        ``on_command`` is accepted for the ObserverEndpoint protocol. The
        WebSocket router is already bound to ``SubjectEngine`` callbacks during
        ``init``.
        """

        del on_command
        await self.observer_event_bus.start()

    async def stop(self) -> None:
        if self._observer_event_bus is not None:
            await self._observer_event_bus.stop()

    async def send_to_session(self, session_id: str, message: dict[str, Any]) -> None:
        await self.connection_manager.send_to(session_id, message)

    async def broadcast(self, message: dict[str, Any]) -> int:
        return await self.connection_manager.broadcast(message)

    async def _forward_core_event(self, subject_event_type: str, payload: Any) -> None:
        del subject_event_type
        if not isinstance(payload, Mapping):
            logger.warning("Ignoring malformed core event payload: %r", payload)
            return
        event_type = payload.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            logger.warning("Ignoring core event payload without event_type: %r", payload)
            return
        await self.observer_event_bus.emit_core_event(
            Message(
                type=event_type,
                payload=_payload_as_dict(payload.get("payload", {})),
            )
        )

    async def _forward_hitl_request(self, subject_event_type: str, payload: Any) -> None:
        del subject_event_type
        await self.observer_event_bus.emit_core_event(
            Message(
                type=EventType.HITL_REQUEST.value,
                payload=_payload_as_dict(payload),
            )
        )


def _create_observer_app(
    config: ObserverServerConfig,
    server: ObserverServer,
    connection_manager: ConnectionManager,
) -> FastAPI:
    app = FastAPI(
        title="ghrah-subject-observer",
        description="ghrah-subject Observer WebSocket server",
        version="0.1.0",
    )

    async def websocket_endpoint(websocket: WebSocket) -> None:
        await server.handle_connection(websocket)

    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "active_sessions": connection_manager.connection_count,
        }

    async def root() -> dict[str, str]:
        return {
            "name": "ghrah-subject-observer",
            "version": "0.1.0",
            "description": "ghrah-subject Observer WebSocket server",
        }

    app.websocket(config.ws_path)(websocket_endpoint)
    app.get("/health")(health)
    app.get("/")(root)
    return app


def _payload_as_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        result = model_dump()
        if isinstance(result, Mapping):
            return dict(result)
    return {"value": payload}
