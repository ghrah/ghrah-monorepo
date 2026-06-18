# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""HITL notary built-in Subject unit."""

from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.hitl.notary import HITLNotary
from ghrah.subject.hitl.policy import HITLPolicy, HITLVerdict
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import HITL_NOTARY, HITL_POLICY
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta

__all__ = ["HITLNotaryUnit"]


class HITLNotaryUnit(SubjectUnit):
    """Owns HITLNotary and hitl_response command handling."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._notary: HITLNotary | None = None
        self._meta = UnitMeta(
            name="hitl_notary",
            requires=frozenset({HITL_POLICY}),
            provides=frozenset({HITL_NOTARY}),
            routes=RouteSpec(
                commands=frozenset({"hitl_response"}),
                events=frozenset({"agent_terminated"}),
            ),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> HITLNotary:
        if self._notary is None:
            raise RuntimeError("HITLNotaryUnit has not been initialized.")
        return self._notary

    async def init(self, ctx: SubjectContext) -> None:
        policy = ctx.services.require(HITL_POLICY)
        if not isinstance(policy, HITLPolicy):
            raise TypeError("HITL_POLICY service must be HITLPolicy.")
        self._notary = HITLNotary(policy)
        ctx.services.set(HITL_NOTARY, self._notary)

    async def stop(self) -> None:
        if self._notary is not None:
            self._notary.cancel_all_promises()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        if command != "hitl_response":
            return {"success": False, "error": f"Unknown HITL command: {command}"}
        return self.handle_response(payload)

    async def handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "agent_terminated":
            self.service.cancel_all_promises(payload.get("name", ""))

    def handle_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        promise_id = payload.get("promise_id", "")
        verdict = HITLVerdict(
            approved=bool(payload.get("approved", False)),
            reason=payload.get("reason") or "",
        )
        resolved = self.service.resolve_promise(promise_id, verdict)
        if not resolved:
            return {
                "success": False,
                "error": f"HITL promise not found or expired: {promise_id}",
            }
        return {
            "success": True,
            "data": {"processed": True, "promise_id": promise_id},
        }
