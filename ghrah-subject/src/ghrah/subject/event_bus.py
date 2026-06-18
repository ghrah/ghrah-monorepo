# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Internal Subject event bus.

This bus is deliberately local to the Subject runtime. It broadcasts
``subject.*`` notifications to in-process handlers and does not provide query
or synchronous subscription APIs.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

__all__ = [
    "SUBJECT_CORE_EVENT_RECEIVED",
    "SUBJECT_HITL_REQUEST_CREATED",
    "SUBJECT_MANIFEST_PERMISSIONS_CHANGED",
    "SUBJECT_TRANSPORT_STATUS_CHANGED",
    "SubjectEventBus",
]

logger = logging.getLogger(__name__)

SUBJECT_CORE_EVENT_RECEIVED = "subject.core_event_received"
SUBJECT_HITL_REQUEST_CREATED = "subject.hitl_request_created"
SUBJECT_MANIFEST_PERMISSIONS_CHANGED = "subject.manifest_permissions_changed"
SUBJECT_TRANSPORT_STATUS_CHANGED = "subject.transport_status_changed"

SubjectEventHandler = Callable[[str, Any], Awaitable[None]]


class SubjectEventBus:
    """Async pub/sub bus for internal Subject runtime notifications."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[SubjectEventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: SubjectEventHandler) -> None:
        """Subscribe an async handler to an internal Subject event type."""

        self._handlers[event_type].append(handler)

    async def emit(self, event_type: str, payload: Any) -> None:
        """Broadcast an event to subscribers with per-handler isolation."""

        handlers = list(self._handlers.get(event_type, ()))
        if not handlers:
            return

        await asyncio.gather(
            *(self._call_handler(event_type, payload, handler) for handler in handlers),
            return_exceptions=True,
        )

    async def _call_handler(
        self,
        event_type: str,
        payload: Any,
        handler: SubjectEventHandler,
    ) -> None:
        try:
            await handler(event_type, payload)
        except Exception:
            logger.warning(
                "Subject event handler failed for %s payload=%s",
                event_type,
                self._summarize_payload(payload),
                exc_info=True,
            )

    @staticmethod
    def _summarize_payload(payload: Any) -> str:
        text = repr(payload)
        if len(text) > 300:
            return f"{text[:297]}..."
        return text
