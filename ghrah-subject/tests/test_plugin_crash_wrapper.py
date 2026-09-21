# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件命令崩溃 wrapper 与超时裁决测试。

不依赖 fiber 状态迁移断言：listener 运行期异常不迁移 fiber
状态，wrapper 层捕获 → on_crash 回调 → failed 回执。
"""

from __future__ import annotations

import asyncio
from typing import Any

from ghrah.plugin.spec import PluginSpec

from ghrah.subject.runtime.ouroboros_bridge import (
    _make_plugin_command_handler,
)
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class _CrashUnit(SubjectUnit):
    """可编程命令行为的最小 unit。"""

    def __init__(self, name: str, behavior) -> None:
        self._meta = UnitMeta(name=name, routes=RouteSpec(commands=frozenset({"do_work"})))
        self._behavior = behavior

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        return await self._behavior(payload)


def _spec(*, timeout_ms: int = 5000, on_timeout: str = "reject") -> PluginSpec:
    return PluginSpec(
        plugin_id="crashy-plugin", version="0.1.0", timeout_ms=timeout_ms, on_timeout=on_timeout
    )


async def test_handler_exception_invokes_on_crash_with_summary() -> None:
    """handler raise → on_crash 被调（plugin_id/command/摘要）+ 回执含插件 id。"""
    crashes: list[tuple[str, str, str]] = []

    async def on_crash(plugin_id: str, command: str, error: str) -> None:
        crashes.append((plugin_id, command, error))

    async def boom(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    handler = _make_plugin_command_handler(
        _CrashUnit("crashy-plugin", boom),
        "do_work",
        CommandContext.internal(),
        spec=_spec(),
        on_crash=on_crash,
    )
    result = await handler({})
    assert result["success"] is False
    assert "plugin crashed: crashy-plugin" in result["error"]
    assert crashes == [("crashy-plugin", "do_work", "RuntimeError: kaboom")]


async def test_timeout_reject_routes_to_crash_path() -> None:
    """timeout_ms 超时 + on_timeout=reject → 崩溃路径。"""
    crashes: list[tuple[str, str, str]] = []

    async def on_crash(plugin_id: str, command: str, error: str) -> None:
        crashes.append((plugin_id, command, error))

    async def slow(payload: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(1.0)
        return {"success": True}

    handler = _make_plugin_command_handler(
        _CrashUnit("crashy-plugin", slow),
        "do_work",
        CommandContext.internal(),
        spec=_spec(timeout_ms=50, on_timeout="reject"),
        on_crash=on_crash,
    )
    result = await handler({})
    assert result["success"] is False
    assert "timeout after 50ms" in result["error"]
    assert crashes[0][0] == "crashy-plugin"
    assert "timeout" in crashes[0][2]


async def test_timeout_allow_with_warn_returns_warn_receipt() -> None:
    """timeout_ms 超时 + on_timeout=allow_with_warn → warn 回执，不卸载。"""
    crashes: list[tuple[str, str, str]] = []

    async def on_crash(plugin_id: str, command: str, error: str) -> None:
        crashes.append((plugin_id, command, error))

    async def slow(payload: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(1.0)
        return {"success": True}

    handler = _make_plugin_command_handler(
        _CrashUnit("crashy-plugin", slow),
        "do_work",
        CommandContext.internal(),
        spec=_spec(timeout_ms=50, on_timeout="allow_with_warn"),
        on_crash=on_crash,
    )
    result = await handler({})
    assert result["success"] is True
    assert "plugin timeout" in result["warning"]
    assert "allow_with_warn" in result["warning"]
    assert crashes == []


async def test_normal_path_passes_through() -> None:
    """正常路径零开销透传（无 wrapper 痕迹）。"""
    crashed = False

    async def on_crash(plugin_id: str, command: str, error: str) -> None:
        nonlocal crashed
        crashed = True

    async def ok(payload: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "data": {"value": 42}}

    handler = _make_plugin_command_handler(
        _CrashUnit("crashy-plugin", ok),
        "do_work",
        CommandContext.internal(),
        spec=_spec(),
        on_crash=on_crash,
    )
    result = await handler({})
    assert result == {"success": True, "data": {"value": 42}}
    assert crashed is False
