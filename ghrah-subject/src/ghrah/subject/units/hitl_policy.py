# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""HITL policy built-in Subject unit."""

from __future__ import annotations

from ghrah.subject.config import SubjectConfig
from ghrah.subject.hitl.policy import HITLPolicy
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import HITL_POLICY, MANIFEST_PERMISSION_INDEX
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta

__all__ = ["HITLPolicyUnit"]


class HITLPolicyUnit(SubjectUnit):
    """Owns the shared HITLPolicy instance."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._policy: HITLPolicy | None = None
        self._meta = UnitMeta(
            name="hitl_policy",
            requires=frozenset({MANIFEST_PERMISSION_INDEX}),
            provides=frozenset({HITL_POLICY}),
            routes=RouteSpec(),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> HITLPolicy:
        if self._policy is None:
            raise RuntimeError("HITLPolicyUnit has not been initialized.")
        return self._policy

    async def init(self, ctx: SubjectContext) -> None:
        manifest_index = ctx.services.require(MANIFEST_PERMISSION_INDEX)
        self._policy = HITLPolicy(
            auto_approve_abilities=ctx.config.hitl.auto_approve_abilities,
            require_approval_by_default=ctx.config.hitl.require_approval_by_default,
            workspace_root=ctx.config.hitl.workspace_root
            or ctx.config.sandbox.workspace_root,
            allowed_paths=ctx.config.hitl.allowed_paths or None,
            manifest_permission_index=manifest_index,
        )
        ctx.services.set(HITL_POLICY, self._policy)
