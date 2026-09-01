# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""热插拔语义专项测试（任务 6，对齐上游 unit_adapter_demo 6 步断言）。

6 步：挂载 → 服务可见 → 命令路由 → 卸载回退（服务 None + Unknown）→
重挂恢复 → 依赖回退。外加 mount_dynamic_unit 的重名防护与幂等卸载。
"""

from __future__ import annotations

from typing import Any

from ouroboros import Context, FiberState  # type: ignore[import-untyped]

from ghrah.subject.runtime.ouroboros_bridge import (
    bridge_command,
    mount_dynamic_unit,
    mount_unit,
    unmount_unit,
    wait_active,
)
from ghrah.subject.runtime.service_keys import SANDBOX_EXECUTOR
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class _ProbeUnit(SubjectUnit):
    """探测单元：提供探测服务 + 一个命令。"""

    def __init__(self, *, name: str = "probe", requires: frozenset[Any] = frozenset()) -> None:
        self._meta = UnitMeta(
            name=name,
            requires=requires,
            routes=RouteSpec(commands=frozenset({"probe_ping"})),
        )
        self.stopped = False

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def init(self, ctx: Any) -> None:
        ctx.provide(f"{self._meta.name}_service", {"unit": self._meta.name})

    async def stop(self) -> None:
        self.stopped = True

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        if command == "probe_ping":
            return {"success": True, "data": {"pong": self._meta.name}}
        return {"success": False, "error": f"Unknown: {command}"}


async def test_hot_plug_six_step_lifecycle() -> None:
    """6 步：挂载 → 服务可见 → 命令路由 → 卸载回退 → 重挂恢复 → 依赖回退。"""
    unit = _ProbeUnit()
    async with Context() as ctx:
        fibers: dict[str, Any] = {}

        # 1. 挂载（ACTIVE + 登记）
        fiber = await mount_dynamic_unit(ctx, unit, fibers)
        assert fiber.state is FiberState.ACTIVE
        assert fibers["probe"] is fiber

        # 2. 服务可见
        assert ctx.get("probe_service") == {"unit": "probe"}

        # 3. 命令路由（ctx.serial 经 mount_unit 注册的路由）
        result = await bridge_command(ctx, "probe_ping", {})
        assert result == {"success": True, "data": {"pong": "probe"}}

        # 4. 卸载回退：服务撤销（None）+ 命令 Unknown + unit.stop 已调
        await unmount_unit(fibers, "probe")
        assert "probe" not in fibers
        assert unit.stopped is True
        assert ctx.get("probe_service", strict=False) is None
        unknown = await bridge_command(ctx, "probe_ping", {})
        assert unknown == {"success": False, "error": "Unknown command: probe_ping"}

        # 5. 重挂恢复：新实例可再次挂载并恢复服务/路由
        unit2 = _ProbeUnit()
        await mount_dynamic_unit(ctx, unit2, fibers)
        assert ctx.get("probe_service") == {"unit": "probe"}
        again = await bridge_command(ctx, "probe_ping", {})
        assert again == {"success": True, "data": {"pong": "probe"}}

        # 6. 依赖回退：required 服务不在场 → PENDING（非死等）；
        #    provide 依赖后 fiber 收敛 ACTIVE
        class _DepUnit(SubjectUnit):
            def __init__(self) -> None:
                self._meta = UnitMeta(
                    name="dep_probe",
                    requires=frozenset({SANDBOX_EXECUTOR}),
                    routes=RouteSpec(commands=frozenset()),
                )

            @property
            def meta(self) -> UnitMeta:
                return self._meta

            async def init(self, ctx: Any) -> None:
                ctx.provide("dep_probe_service", {"ok": True})

        dep_unit = _DepUnit()
        dep_fiber = ctx.plugin(mount_unit(dep_unit))
        await _wait_pending(dep_fiber)
        assert ctx.get("dep_probe_service", strict=False) is None

        # provide 依赖 → fiber 转 ACTIVE
        ctx.provide(SANDBOX_EXECUTOR.name, object())
        await wait_active(dep_fiber, timeout=5.0)
        assert ctx.get("dep_probe_service") == {"ok": True}


async def _wait_pending(fiber: Any) -> None:
    """等 fiber 进入 PENDING 稳态（inject 未满足）。"""
    import asyncio

    for _ in range(100):
        if fiber.state is FiberState.PENDING:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"fiber did not reach PENDING: {fiber.state}")


async def test_mount_dynamic_duplicate_name_rejected() -> None:
    async with Context() as ctx:
        fibers: dict[str, Any] = {}
        await mount_dynamic_unit(ctx, _ProbeUnit(), fibers)

        import pytest

        with pytest.raises(ValueError, match="already mounted"):
            await mount_dynamic_unit(ctx, _ProbeUnit(), fibers)


async def test_unmount_unknown_name_is_idempotent() -> None:
    fibers: dict[str, Any] = {}
    await unmount_unit(fibers, "ghost")  # 无异常
    assert fibers == {}
