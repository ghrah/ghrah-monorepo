# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Action-chain ledger built-in Subject unit."""

from __future__ import annotations

import logging
from typing import Any

from ghrah.context.persistence import serialize_node  # type: ignore[import-untyped]
from ghrah.subject.config import SubjectConfig
from ghrah.subject.ledger.chain import ActionChainLedger
from ghrah.subject.persistence.service import SubjectPersistenceService
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import LEDGER, PERSISTENCE
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import CHAIN_HISTORY_COMMANDS

__all__ = ["LedgerUnit"]

logger = logging.getLogger(__name__)


class LedgerUnit(SubjectUnit):
    """Owns ActionChainLedger and action-chain command/event routes."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ledger: ActionChainLedger | None = None
        self._meta = UnitMeta(
            name="ledger",
            requires=frozenset({PERSISTENCE}),
            provides=frozenset({LEDGER}),
            routes=RouteSpec(
                commands=CHAIN_HISTORY_COMMANDS,
                events=frozenset({"action_chain_updated"}),
            ),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> ActionChainLedger:
        if self._ledger is None:
            raise RuntimeError("LedgerUnit has not been initialized.")
        return self._ledger

    async def init(self, ctx: SubjectContext) -> None:
        persistence = ctx.services.require(PERSISTENCE)
        if not isinstance(persistence, SubjectPersistenceService):
            raise TypeError("PERSISTENCE service must be SubjectPersistenceService.")
        self._ledger = ActionChainLedger(persistence)
        ctx.services.set(LEDGER, self._ledger)

    async def start(self) -> None:
        await self.service.start()

    async def stop(self) -> None:
        if self._ledger is not None:
            await self._ledger.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        if command not in CHAIN_HISTORY_COMMANDS:
            return {"success": False, "error": f"Unknown ledger command: {command}"}
        return self._handle_chain_history(payload)

    async def handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type != "action_chain_updated":
            return
        agent_name = payload.get("agent_name", "")
        node_data = payload.get("node", {})
        if not agent_name:
            return
        await self.service.append_node(agent_name, node_data)

    def _handle_chain_history(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_name = payload.get("agent_name", "")
        branch_name = payload.get("branch_name", "main")
        limit = payload.get("limit", -1)

        if not agent_name:
            return {"success": False, "error": "agent_name is required"}

        try:
            nodes = self.service.get_chain_history(
                agent_name,
                branch=branch_name,
                limit=limit,
            )
            serialized = [serialize_node(node) for node in nodes]
            active_session_id = ""
            meta = self.service.get_chain_meta(agent_name)
            if meta is not None:
                active_session_id = meta.active_session_id
            return {
                "success": True,
                "data": {
                    "agent_name": agent_name,
                    "branch_name": branch_name,
                    "nodes": serialized,
                    "active_session_id": active_session_id,
                },
            }
        except Exception as exc:
            logger.exception("Failed to get chain history for %s", agent_name)
            return {"success": False, "error": str(exc)}
