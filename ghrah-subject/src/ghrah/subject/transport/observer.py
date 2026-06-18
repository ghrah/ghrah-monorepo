# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Observer endpoint protocol for Subject runtime adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

__all__ = ["ObserverCommandHandler", "ObserverEndpoint", "ObserverMessage"]

ObserverMessage = dict[str, Any]
ObserverCommandHandler = Callable[
    [str, dict[str, Any], str | None, str | None],
    Awaitable[dict[str, Any]],
]


class ObserverEndpoint(Protocol):
    """Service boundary for Observer-facing transport adapters."""

    async def start(self, on_command: ObserverCommandHandler) -> None:
        """Start the endpoint with an observer command callback."""

    async def stop(self) -> None:
        """Stop accepting observer commands."""

    async def send_to_session(self, session_id: str, message: ObserverMessage) -> None:
        """Send a message to one observer session."""

    async def broadcast(self, message: ObserverMessage) -> int:
        """Broadcast a message to observer sessions."""
