# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Permission checker built-in Subject unit."""

from __future__ import annotations

from ghrah.subject.config import SubjectConfig
from ghrah.subject.permission_checker import PermissionChecker
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import (
    MANIFEST_PERMISSION_INDEX,
    PERMISSION_SERVICE,
)
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta

__all__ = ["PermissionsUnit"]


class PermissionsUnit(SubjectUnit):
    """Owns the shared PermissionChecker instance."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._checker: PermissionChecker | None = None
        self._meta = UnitMeta(
            name="permissions",
            requires=frozenset({MANIFEST_PERMISSION_INDEX}),
            provides=frozenset({PERMISSION_SERVICE}),
            routes=RouteSpec(),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> PermissionChecker:
        if self._checker is None:
            raise RuntimeError("PermissionsUnit has not been initialized.")
        return self._checker

    async def init(self, ctx: SubjectContext) -> None:
        manifest_index = ctx.services.require(MANIFEST_PERMISSION_INDEX)
        self._checker = PermissionChecker(
            allowed_paths=ctx.config.hitl.allowed_paths or None,
            workspace_root=ctx.config.hitl.workspace_root
            or ctx.config.sandbox.workspace_root,
            require_approval=ctx.config.hitl.require_approval_by_default,
            manifest_permission_index=manifest_index,
        )
        ctx.services.set(PERMISSION_SERVICE, self._checker)
