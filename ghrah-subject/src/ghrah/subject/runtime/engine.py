# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Subject runtime engine."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from importlib.metadata import entry_points
from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SubjectEventBus
from ghrah.subject.runtime.capability import CapabilityRegistry
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.dependency import topological_sort
from ghrah.subject.runtime.dispatcher import MessageDispatcher
from ghrah.subject.runtime.service_keys import CAPABILITY_REGISTRY, RECONCILIATION_SERVICE
from ghrah.subject.runtime.services import SubjectServices
from ghrah.subject.unit.base import SubjectUnit, UnitState

__all__ = ["SubjectEngine"]

logger = logging.getLogger(__name__)

DiscoveredUnit = SubjectUnit | Callable[[], SubjectUnit]


class SubjectEngine:
    """Thin assembly layer for Subject runtime units."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._event_bus = SubjectEventBus()
        self._services = SubjectServices()
        self._capability_registry = CapabilityRegistry()
        self._services.set(CAPABILITY_REGISTRY, self._capability_registry)
        self._units: dict[str, SubjectUnit] = {}
        self._states: dict[str, UnitState] = {}
        self._discovered: dict[str, DiscoveredUnit] = {}
        self._context: SubjectContext | None = None
        self._dispatcher: MessageDispatcher | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._start_order: list[str] = []
        self._started = False

    @property
    def config(self) -> SubjectConfig:
        """Return runtime configuration."""

        return self._config

    @property
    def event_bus(self) -> SubjectEventBus:
        """Return the internal event bus."""

        return self._event_bus

    @property
    def services(self) -> SubjectServices:
        """Return runtime services."""

        return self._services

    @property
    def capability_registry(self) -> CapabilityRegistry:
        """Return the seeded capability registry."""

        return self._capability_registry

    @property
    def context(self) -> SubjectContext:
        """Return the created runtime context."""

        if self._context is None:
            raise RuntimeError("SubjectEngine has not been started.")
        return self._context

    @property
    def dispatcher(self) -> MessageDispatcher:
        """Return the created dispatcher."""

        if self._dispatcher is None:
            raise RuntimeError("SubjectEngine has not been started.")
        return self._dispatcher

    @property
    def discovered(self) -> dict[str, DiscoveredUnit]:
        """Return discovered third-party unit candidates."""

        return dict(self._discovered)

    def register_unit(self, unit: SubjectUnit) -> None:
        """Register a unit instance with the engine."""

        unit_name = unit.meta.name
        if unit_name in self._units:
            raise ValueError(f"Subject unit '{unit_name}' is already registered.")
        self._units[unit_name] = unit
        self._states[unit_name] = UnitState.REGISTERED

    def register_builtin_units(self, *, profile: str = "coexistence") -> None:
        """Register built-in units for the requested runtime profile."""

        from ghrah.subject.units import register_builtin_units

        register_builtin_units(self, profile=profile)
        logger.info("Registered Subject built-in units (profile=%s).", profile)

    def discover(self, group: str = "ghrah.subject.units") -> None:
        """Discover third-party unit candidates without enabling them."""

        try:
            discovered: Any = entry_points()
            selected = (
                discovered.select(group=group)
                if hasattr(discovered, "select")
                else discovered.get(group, ())
            )
        except Exception:
            logger.exception("Failed to inspect Subject unit entry points.")
            return

        for entry_point in selected:
            try:
                loaded = entry_point.load()
            except Exception:
                logger.exception(
                    "Failed to load Subject unit entry point '%s'.",
                    entry_point.name,
                )
                continue
            self._discovered[entry_point.name] = loaded

    def enable_from_config(self) -> None:
        """Enable third-party units listed in the config allowlist."""

        for unit_name in self._config.enabled_third_party_units:
            discovered = self._discovered.get(unit_name)
            if discovered is None:
                logger.warning(
                    "Subject unit '%s' is enabled in config but was not discovered.",
                    unit_name,
                )
                continue
            self.register_unit(self._instantiate_discovered(unit_name, discovered))

    def validate(self) -> list[SubjectUnit]:
        """Validate dependencies and return topological unit order."""

        return topological_sort(self._units, runtime_services={CAPABILITY_REGISTRY})

    async def start(self) -> None:
        """Initialize and start units in dependency order."""

        if self._started:
            return

        ordered_units = self.validate()
        self._start_order = [unit.meta.name for unit in ordered_units]

        context = SubjectContext(
            engine=self,
            config=self._config,
            event_bus=self._event_bus,
            services=self._services,
            units=self._units,
            create_task=self._create_task,
        )
        dispatcher = MessageDispatcher(context)
        context.attach_dispatcher(dispatcher)
        dispatcher.rebuild()
        self._context = context
        self._dispatcher = dispatcher

        initialized: list[SubjectUnit] = []
        current_unit: SubjectUnit | None = None
        try:
            for unit in ordered_units:
                current_unit = unit
                await unit.init(context)
                initialized.append(unit)
                self._states[unit.meta.name] = UnitState.INITIALIZED

            for unit in ordered_units:
                current_unit = unit
                await unit.start()
                self._states[unit.meta.name] = UnitState.STARTED

        except Exception:
            if current_unit is not None:
                self._states[current_unit.meta.name] = UnitState.FAILED
            await self._rollback_start(initialized, current_unit)
            raise

        self._started = True

        if self._config.recovery.enabled and self._config.recovery.reconcile_on_start:
            try:
                reconcile_service = self._context.services.require(RECONCILIATION_SERVICE)
                await reconcile_service.reconcile()
            except Exception:
                logger.exception("reconcile on start failed (non-fatal)")

    async def dispatch_observer_command(
        self,
        command: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch an Observer command through the runtime dispatcher."""

        return await self.dispatcher.dispatch_observer_command(
            command,
            payload,
            request_id=request_id,
            session_id=session_id,
        )

    async def run_forever(self) -> None:
        """Start the engine and keep it alive until cancelled."""

        await self.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop background tasks and units in reverse dependency order."""

        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

        for unit_name in reversed(self._start_order):
            unit = self._units[unit_name]
            state = self._states.get(unit_name)
            if state in {
                UnitState.INITIALIZED,
                UnitState.STARTED,
                UnitState.READY,
                UnitState.STOPPING,
            }:
                self._states[unit_name] = UnitState.STOPPING
                try:
                    await unit.stop()
                except Exception:
                    logger.exception("Subject unit '%s' failed during stop.", unit_name)
                    self._states[unit_name] = UnitState.FAILED
                else:
                    self._states[unit_name] = UnitState.STOPPED

        self._started = False

    def get_unit(self, name: str) -> SubjectUnit | None:
        """Return a registered unit."""

        return self._units.get(name)

    def get_state(self, name: str) -> UnitState | None:
        """Return a unit lifecycle state."""

        return self._states.get(name)

    def _create_task(self, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        async def run() -> Any:
            return await coro

        task: asyncio.Task[Any] = asyncio.create_task(run())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _rollback_start(
        self,
        initialized: list[SubjectUnit],
        failed_unit: SubjectUnit | None,
    ) -> None:
        for unit in reversed(initialized):
            unit_name = unit.meta.name
            try:
                await unit.stop()
            except Exception:
                logger.exception("Subject unit '%s' failed during start rollback.", unit_name)
                self._states[unit_name] = UnitState.FAILED
            else:
                self._states[unit_name] = UnitState.STOPPED
        if failed_unit is not None:
            self._states[failed_unit.meta.name] = UnitState.FAILED
        self._started = False

    @staticmethod
    def _instantiate_discovered(unit_name: str, discovered: DiscoveredUnit) -> SubjectUnit:
        unit = discovered if isinstance(discovered, SubjectUnit) else discovered()
        if not isinstance(unit, SubjectUnit):
            raise TypeError(
                f"Discovered Subject unit '{unit_name}' did not produce a SubjectUnit."
            )
        return unit
