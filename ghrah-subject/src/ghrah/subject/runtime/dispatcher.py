# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Message dispatcher for Subject runtime units."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from ghrah.protocol.types import SystemType  # type: ignore[import-untyped]
from ghrah.subject.event_bus import SUBJECT_CORE_EVENT_RECEIVED
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.transport.core import CoreTransport
from ghrah.subject.unit.base import CommandContext, SubjectUnit

__all__ = ["CommandRoute", "MessageDispatcher"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandRoute:
    """A command route declared by a unit."""

    unit: SubjectUnit
    is_long_running: bool = False


class MessageDispatcher:
    """Routes Core and Observer messages to Subject units."""

    def __init__(self, ctx: SubjectContext) -> None:
        self._ctx = ctx
        self._command_routes: dict[str, CommandRoute] = {}
        self._event_routes: dict[str, list[SubjectUnit]] = defaultdict(list)

    @property
    def command_routes(self) -> Mapping[str, CommandRoute]:
        """Return command routes."""

        return self._command_routes

    @property
    def event_routes(self) -> Mapping[str, list[SubjectUnit]]:
        """Return event routes."""

        return self._event_routes

    def rebuild(self) -> None:
        """Rebuild routes from registered unit metadata."""

        self._command_routes.clear()
        self._event_routes.clear()

        for unit in self._ctx.units.values():
            meta = unit.meta
            for command in meta.routes.commands:
                self._add_command_route(command, CommandRoute(unit=unit))
            for command in meta.routes.long_running_commands:
                self._add_command_route(command, CommandRoute(unit=unit, is_long_running=True))
            for event_type in meta.routes.events:
                self._event_routes[event_type].append(unit)

    async def dispatch_core_message(
        self,
        message: Mapping[str, Any] | Any,
        *,
        source: CoreTransport,
    ) -> None:
        """Dispatch one inbound Core message.

        ``source``（D1）为接收到该消息的 transport 自身：resolve / pong / reply
        回路由经 ``source``（替换原单一 ``ctx.core_transport``），保证非默认
        cluster 的回执在接收到它的那个 transport 的 tracker 上 resolve。
        """

        msg = _message_to_dict(message)
        msg_type = _message_type(msg)
        payload = _payload_as_dict(msg.get("payload", {}))
        request_id = _request_id(msg, payload)

        if msg_type == SystemType.COMMAND_RESULT.value:
            if request_id is not None:
                source.resolve_command_result(request_id, payload)
            return

        if msg_type == SystemType.PING.value:
            await source.send({"type": SystemType.PONG.value})
            return

        route = self._command_routes.get(msg_type)
        if route is not None:
            cmd_ctx = CommandContext.core(
                request_id,
                timeout=self._ctx.config.core.command_timeout,
            )
            if route.is_long_running:
                self._ctx.create_task(
                    self._dispatch_core_command(route, msg_type, payload, cmd_ctx, source)
                )
                return
            await self._dispatch_core_command(route, msg_type, payload, cmd_ctx, source)
            return

        if msg_type in self._event_routes:
            await self._dispatch_core_event(msg_type, payload)
            return

        logger.warning("No Subject runtime route for Core message type '%s'.", msg_type)

    async def dispatch_observer_command(
        self,
        command: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch an Observer-originated command and return its result."""

        route = self._command_routes.get(command)
        if route is None:
            logger.warning("No Subject runtime route for Observer command '%s'.", command)
            return {"success": False, "error": f"Unknown command: {command}"}

        cmd_ctx = CommandContext.observer(
            request_id,
            session_id=session_id,
            timeout=self._ctx.config.core.command_timeout,
        )
        return await self._call_unit(route.unit, command, payload, cmd_ctx)

    def _add_command_route(self, command: str, route: CommandRoute) -> None:
        existing = self._command_routes.get(command)
        if existing is not None:
            raise ValueError(
                f"Command route conflict for '{command}': "
                f"{existing.unit.meta.name}, {route.unit.meta.name}."
            )
        self._command_routes[command] = route

    async def _dispatch_core_command(
        self,
        route: CommandRoute,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
        source: CoreTransport,
    ) -> None:
        result = await self._call_unit(route.unit, command, payload, cmd_ctx)
        response_payload = dict(result)
        if cmd_ctx.request_id is not None and "request_id" not in response_payload:
            response_payload["request_id"] = cmd_ctx.request_id
        await source.send(
            {
                "type": SystemType.COMMAND_RESULT.value,
                "payload": response_payload,
                "request_id": cmd_ctx.request_id,
            }
        )

    async def _dispatch_core_event(self, event_type: str, payload: dict[str, Any]) -> None:
        units = list(self._event_routes.get(event_type, ()))
        await asyncio.gather(
            *(self._call_event_handler(unit, event_type, payload) for unit in units),
            return_exceptions=True,
        )
        await self._ctx.event_bus.emit(
            SUBJECT_CORE_EVENT_RECEIVED,
            {"event_type": event_type, "payload": payload},
        )

    async def _call_event_handler(
        self,
        unit: SubjectUnit,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            await unit.handle_event(event_type, payload)
        except Exception:
            logger.exception(
                "Subject unit '%s' failed handling event '%s'.",
                unit.meta.name,
                event_type,
            )
            raise

    async def _call_unit(
        self,
        unit: SubjectUnit,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        try:
            return await unit.handle_command(command, payload, cmd_ctx)
        except Exception as e:
            logger.exception(
                "Subject unit '%s' failed handling command '%s' request_id=%s.",
                unit.meta.name,
                command,
                cmd_ctx.request_id,
            )
            return {"success": False, "error": str(e)}


def _message_to_dict(message: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(message, Mapping):
        return dict(message)
    model_dump = getattr(message, "model_dump", None)
    if callable(model_dump):
        return cast(dict[str, Any], model_dump())
    raise TypeError(f"Unsupported message type: {type(message)!r}")


def _payload_as_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        return cast(dict[str, Any], model_dump())
    return {"value": payload}


def _message_type(message: Mapping[str, Any]) -> str:
    value = message.get("type", "")
    return value if isinstance(value, str) else str(value)


def _request_id(message: Mapping[str, Any], payload: Mapping[str, Any]) -> str | None:
    value = message.get("request_id") or payload.get("request_id")
    return value if isinstance(value, str) and value else None
