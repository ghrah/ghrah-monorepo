from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SubjectEventBus
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.dispatcher import MessageDispatcher
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import (
    CAPABILITY_REGISTRY,
    CORE_TRANSPORT,
    OBSERVER_ENDPOINT,
)
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.transport.core import InProcessCoreTransport
from ghrah.subject.transport.observer import ObserverCommandHandler
from ghrah.subject.unit.base import SubjectUnit, UnitMeta


class _Unit(SubjectUnit):
    @property
    def meta(self) -> UnitMeta:
        return UnitMeta(name="unit")


class _ObserverEndpoint:
    async def start(self, on_command: ObserverCommandHandler) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_to_session(self, session_id: str, message: dict[str, Any]) -> None:
        return None

    async def broadcast(self, message: dict[str, Any]) -> int:
        return 0


def _create_context(
    services: SubjectServices | None = None,
) -> SubjectContext:
    unit = _Unit()

    def create_task(coro: Any) -> asyncio.Task[Any]:
        return asyncio.create_task(coro)

    return SubjectContext(
        engine=SubjectEngine(SubjectConfig()),
        config=SubjectConfig(),
        event_bus=SubjectEventBus(),
        services=services or SubjectServices(),
        units={"unit": unit},
        create_task=create_task,
    )


async def test_context_uses_constructor_injected_units_and_task_factory() -> None:
    ctx = _create_context()

    async def work() -> str:
        return "done"

    task = ctx.create_task(work())

    assert ctx.get_unit("unit") is not None
    assert ctx.get_unit("missing") is None
    assert await task == "done"


def test_dispatcher_access_requires_attach() -> None:
    ctx = _create_context()

    with pytest.raises(RuntimeError, match="dispatcher has not been attached"):
        _ = ctx.dispatcher

    dispatcher = MessageDispatcher(ctx)
    ctx.attach_dispatcher(dispatcher)

    assert ctx.dispatcher is dispatcher
    with pytest.raises(RuntimeError, match="already attached"):
        ctx.attach_dispatcher(dispatcher)


def test_convenience_properties_require_typed_services() -> None:
    services = SubjectServices()
    transport = InProcessCoreTransport()
    endpoint = _ObserverEndpoint()
    registry = CapabilityRegistry()
    services.set(CORE_TRANSPORT, transport)
    services.set(OBSERVER_ENDPOINT, endpoint)
    services.set(CAPABILITY_REGISTRY, registry)
    ctx = _create_context(services)

    assert ctx.core_transport is transport
    assert ctx.observer_endpoint is endpoint
    assert ctx.capability_registry is registry


def test_missing_convenience_service_raises_clear_error() -> None:
    ctx = _create_context()

    with pytest.raises(RuntimeError, match="core_transport"):
        _ = ctx.core_transport
