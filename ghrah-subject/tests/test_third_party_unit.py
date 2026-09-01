# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""第三方 Subject Unit 发现与 allowlist 启用验收（Ouroboros 形态）。

验证三段（定位文档 §原则9 语义保留）：
1. ``discover()`` 经 entry_points group 发现候选（不启用）。
2. 默认 allowlist 空 → ``mount_third_party_units`` 挂载零 unit。
3. allowlist 启用 → ``ctx.plugin(mount_unit(unit))`` 挂载 + 命令经
   ctx.serial 路由可达。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ouroboros import Context, FiberState  # type: ignore[import-untyped]

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command
from ghrah.subject.runtime.third_party import (
    discover,
    mount_third_party_units,
    resolve_discovered,
)
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class AuditLogUnit(SubjectUnit):
    """Fake 第三方 Unit：审计日志，记录命令。"""

    def __init__(self) -> None:
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self._meta = UnitMeta(
            name="audit_log",
            routes=RouteSpec(commands=frozenset({"audit_query"})),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        self.commands.append((command, dict(payload)))
        if command == "audit_query":
            return {"success": True, "data": {"records": len(self.commands)}}
        return {"success": False, "error": f"Unknown: {command}"}


def _config(tmp_path: Path, *, allowlist: list[str]) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
        enabled_third_party_units=allowlist,
    )


def test_resolve_discovered_instantiates_and_validates() -> None:
    unit = resolve_discovered("audit_log", AuditLogUnit)
    assert isinstance(unit, AuditLogUnit)

    import pytest

    with pytest.raises(TypeError):
        resolve_discovered("bad", lambda: object())  # type: ignore[arg-type,return-value]


def test_discover_returns_candidates_without_enabling() -> None:
    candidates = discover()
    # 本包 entry_points group 为空（内置 unit 显式挂载）；发现≠启用语义仍在
    assert isinstance(candidates, dict)


async def test_allowlist_empty_mounts_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path, allowlist=[])
    async with Context() as ctx:
        fibers = await mount_third_party_units(ctx, config, discovered={"audit_log": AuditLogUnit})
        assert fibers == {}


async def test_allowlist_enables_unit_and_command_routes(tmp_path: Path) -> None:
    config = _config(tmp_path, allowlist=["audit_log"])
    async with Context() as ctx:
        fibers = await mount_third_party_units(ctx, config, discovered={"audit_log": AuditLogUnit})
        assert set(fibers) == {"audit_log"}
        assert fibers["audit_log"].state is FiberState.ACTIVE

        # 命令经 ctx.serial 路由可达（bridge_command → command/audit_query）
        result = await bridge_command(ctx, "audit_query", {})
        assert result["success"] is True
        assert result["data"]["records"] == 1


async def test_allowlisted_but_not_discovered_warns_and_skips(tmp_path: Path) -> None:
    config = _config(tmp_path, allowlist=["ghost"])
    async with Context() as ctx:
        fibers = await mount_third_party_units(ctx, config, discovered={})
        assert fibers == {}
