# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Runtime context handed to Subject units."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SubjectEventBus
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.runtime.service_keys import (
    CAPABILITY_REGISTRY,
    CORE_TRANSPORT,
    OBSERVER_ENDPOINT,
)
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.transport.core import CoreTransport
from ghrah.subject.transport.observer import ObserverEndpoint
from ghrah.subject.unit.base import SubjectUnit

if TYPE_CHECKING:
    from ghrah.subject.runtime.dispatcher import MessageDispatcher
    from ghrah.subject.runtime.engine import SubjectEngine

__all__ = ["SubjectContext"]


class SubjectContext:
    """Runtime dependencies exposed to Subject units."""

    def __init__(
        self,
        *,
        engine: SubjectEngine,
        config: SubjectConfig,
        event_bus: SubjectEventBus,
        services: SubjectServices,
        units: Mapping[str, SubjectUnit],
        create_task: Callable[[Awaitable[Any]], asyncio.Task[Any]],
    ) -> None:
        self._engine = engine
        self._config = config
        self._event_bus = event_bus
        self._services = services
        self._units = units
        self._create_task = create_task
        self._dispatcher: MessageDispatcher | None = None

    @property
    def engine(self) -> SubjectEngine:
        """Return the owning engine."""

        return self._engine

    @property
    def config(self) -> SubjectConfig:
        """Return Subject configuration."""

        return self._config

    @property
    def event_bus(self) -> SubjectEventBus:
        """Return the internal event bus."""

        return self._event_bus

    @property
    def services(self) -> SubjectServices:
        """Return the typed service registry."""

        return self._services

    @property
    def units(self) -> Mapping[str, SubjectUnit]:
        """Return registered units by name."""

        return self._units

    @property
    def dispatcher(self) -> MessageDispatcher:
        """Return the attached dispatcher."""

        if self._dispatcher is None:
            raise RuntimeError("SubjectContext dispatcher has not been attached.")
        return self._dispatcher

    @property
    def core_transport(self) -> CoreTransport:
        """Return the required Core transport service."""

        return self._services.require(CORE_TRANSPORT)

    @property
    def observer_endpoint(self) -> ObserverEndpoint:
        """Return the required Observer endpoint service."""

        return self._services.require(OBSERVER_ENDPOINT)

    @property
    def capability_registry(self) -> CapabilityRegistry:
        """Return the runtime capability registry."""

        return self._services.require(CAPABILITY_REGISTRY)

    def attach_dispatcher(self, dispatcher: MessageDispatcher) -> None:
        """Attach the dispatcher after both context and dispatcher exist."""

        if self._dispatcher is not None:
            raise RuntimeError("SubjectContext dispatcher is already attached.")
        self._dispatcher = dispatcher

    def get_unit(self, name: str) -> SubjectUnit | None:
        """Return a registered unit by name."""

        return self._units.get(name)

    def create_task(self, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        """Create a managed background task."""

        return self._create_task(coro)
