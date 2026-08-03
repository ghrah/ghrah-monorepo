from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from ghrah.protocol.types import SystemType  # type: ignore[import-untyped]

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SUBJECT_CORE_EVENT_RECEIVED, SubjectEventBus
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.dispatcher import MessageDispatcher
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import CAPABILITY_REGISTRY
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.transport.core import InProcessCoreTransport
from ghrah.subject.unit.base import (
    CommandContext,
    CommandSource,
    RouteSpec,
    SubjectUnit,
    UnitMeta,
)


class _Unit(SubjectUnit):
    def __init__(
        self,
        name: str,
        *,
        commands: frozenset[str] = frozenset(),
        long_running_commands: frozenset[str] = frozenset(),
        events: frozenset[str] = frozenset(),
        result: dict[str, Any] | None = None,
        command_error: Exception | None = None,
        event_error: Exception | None = None,
    ) -> None:
        self._meta = UnitMeta(
            name=name,
            routes=RouteSpec(
                commands=commands,
                long_running_commands=long_running_commands,
                events=events,
            ),
        )
        self.result = result or {"success": True, "data": {"unit": name}}
        self.command_error = command_error
        self.event_error = event_error
        self.commands_seen: list[tuple[str, dict[str, Any], CommandContext]] = []
        self.events_seen: list[tuple[str, dict[str, Any]]] = []

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        self.commands_seen.append((command, payload, cmd_ctx))
        if self.command_error is not None:
            raise self.command_error
        return dict(self.result)

    async def handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events_seen.append((event_type, payload))
        if self.event_error is not None:
            raise self.event_error


class _Harness:
    def __init__(self, units: list[_Unit]) -> None:
        self.transport = InProcessCoreTransport()
        self.event_bus = SubjectEventBus()
        self.services = SubjectServices()
        self.services.set(CAPABILITY_REGISTRY, CapabilityRegistry())
        self.created_tasks: list[asyncio.Task[Any]] = []
        self.ctx = SubjectContext(
            engine=SubjectEngine(SubjectConfig()),
            config=SubjectConfig(),
            event_bus=self.event_bus,
            services=self.services,
            units={unit.meta.name: unit for unit in units},
            create_task=self.create_task,
        )
        self.dispatcher = MessageDispatcher(self.ctx)
        self.ctx.attach_dispatcher(self.dispatcher)
        self.dispatcher.rebuild()

    def create_task(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self.created_tasks.append(task)
        return task

    async def start_transport(self) -> None:
        await self.transport.start(self.dispatcher.dispatch_core_message)


async def test_core_command_routes_to_unit_and_sends_command_result() -> None:
    unit = _Unit("commands", commands=frozenset({"do_work"}))
    harness = _Harness([unit])
    await harness.start_transport()

    await harness.dispatcher.dispatch_core_message(
        {"type": "do_work", "payload": {"x": 1}, "request_id": "req-1"},
        source=harness.transport,
    )

    command, payload, cmd_ctx = unit.commands_seen[0]
    sent = harness.transport.sent_messages[-1]

    assert command == "do_work"
    assert payload == {"x": 1}
    assert cmd_ctx.source == CommandSource.CORE
    assert cmd_ctx.request_id == "req-1"
    assert sent["type"] == SystemType.COMMAND_RESULT.value
    assert sent["payload"]["success"] is True
    assert sent["payload"]["request_id"] == "req-1"


async def test_long_running_core_command_uses_background_task() -> None:
    unit = _Unit("long", long_running_commands=frozenset({"slow"}))
    harness = _Harness([unit])
    await harness.start_transport()

    await harness.dispatcher.dispatch_core_message(
        {"type": "slow", "payload": {}, "request_id": "req-1"},
        source=harness.transport,
    )

    assert len(harness.created_tasks) == 1
    await harness.created_tasks[0]
    assert harness.transport.sent_messages[-1]["type"] == SystemType.COMMAND_RESULT.value


async def test_observer_command_returns_result_without_core_response() -> None:
    unit = _Unit("observer", commands=frozenset({"local"}))
    harness = _Harness([unit])
    await harness.start_transport()

    result = await harness.dispatcher.dispatch_observer_command(
        "local",
        {"y": 2},
        request_id="obs-1",
        session_id="session-1",
    )

    _, _, cmd_ctx = unit.commands_seen[0]
    assert result["success"] is True
    assert cmd_ctx.source == CommandSource.OBSERVER
    assert cmd_ctx.request_id == "obs-1"
    assert cmd_ctx.session_id == "session-1"
    assert harness.transport.sent_messages == []


async def test_core_event_multicasts_to_units_and_internal_event_bus() -> None:
    first = _Unit("first", events=frozenset({"agent_spawned"}))
    second = _Unit("second", events=frozenset({"agent_spawned"}))
    harness = _Harness([first, second])
    emitted: list[tuple[str, Any]] = []

    async def on_internal(event_type: str, payload: Any) -> None:
        emitted.append((event_type, payload))

    harness.event_bus.subscribe(SUBJECT_CORE_EVENT_RECEIVED, on_internal)

    await harness.dispatcher.dispatch_core_message(
        {"type": "agent_spawned", "payload": {"name": "agent-a"}},
        source=harness.transport,
    )

    assert first.events_seen == [("agent_spawned", {"name": "agent-a"})]
    assert second.events_seen == [("agent_spawned", {"name": "agent-a"})]
    assert emitted == [
        (
            SUBJECT_CORE_EVENT_RECEIVED,
            {"event_type": "agent_spawned", "payload": {"name": "agent-a"}},
        )
    ]


async def test_event_handler_failure_is_isolated(caplog: Any) -> None:
    bad = _Unit(
        "bad",
        events=frozenset({"agent_spawned"}),
        event_error=RuntimeError("event boom"),
    )
    good = _Unit("good", events=frozenset({"agent_spawned"}))
    harness = _Harness([bad, good])

    with caplog.at_level(logging.ERROR):
        await harness.dispatcher.dispatch_core_message(
            {"type": "agent_spawned", "payload": {"name": "agent-a"}},
            source=harness.transport,
        )

    assert good.events_seen == [("agent_spawned", {"name": "agent-a"})]
    assert "bad" in caplog.text
    assert "agent_spawned" in caplog.text


async def test_command_handler_failure_sends_failure_result(caplog: Any) -> None:
    unit = _Unit(
        "commands",
        commands=frozenset({"do_work"}),
        command_error=RuntimeError("command boom"),
    )
    harness = _Harness([unit])
    await harness.start_transport()

    with caplog.at_level(logging.ERROR):
        await harness.dispatcher.dispatch_core_message(
            {"type": "do_work", "payload": {}, "request_id": "req-1"},
            source=harness.transport,
        )

    sent = harness.transport.sent_messages[-1]
    assert sent["payload"]["success"] is False
    assert sent["payload"]["error"] == "command boom"
    assert "commands" in caplog.text
    assert "do_work" in caplog.text


async def test_command_result_resolves_pending_transport_request() -> None:
    harness = _Harness([])
    await harness.start_transport()
    request_task = asyncio.create_task(
        harness.transport.send_and_wait(
            {"type": "request", "request_id": "req-1"},
            timeout=1.0,
        )
    )
    await asyncio.sleep(0)

    await harness.dispatcher.dispatch_core_message(
        {"type": "command_result", "payload": {"success": True}, "request_id": "req-1"},
        source=harness.transport,
    )

    assert await request_task == {"success": True}


async def test_ping_sends_pong() -> None:
    harness = _Harness([])
    await harness.start_transport()

    await harness.dispatcher.dispatch_core_message({"type": "ping"}, source=harness.transport)

    assert harness.transport.sent_messages == [{"type": "pong"}]


def test_rebuild_rejects_command_route_conflicts() -> None:
    first = _Unit("first", commands=frozenset({"same"}))
    second = _Unit("second", commands=frozenset({"same"}))

    with pytest.raises(ValueError, match="same"):
        _Harness([first, second])


async def test_unmatched_core_message_warns(caplog: Any) -> None:
    harness = _Harness([])

    with caplog.at_level(logging.WARNING):
        await harness.dispatcher.dispatch_core_message(
            {"type": "unknown"}, source=harness.transport
        )

    assert "No Subject runtime route" in caplog.text
