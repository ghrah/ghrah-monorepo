# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""bridge_command 消歧防御约定测试。

聚合裁决（1787900000000）后 subject 四件套剔除，``execute_ability``/
``hitl_response`` 的实际冲突面消失（CoreUnit 17 命令唯一归宿）。本文件
固化「None 穿透 + 挂载顺序 + 双 None 兜底」作为**第三方同名命令**的防御
约定：handler 返回 None = 「不是我的」，穿透给下一个；全 None →
Unknown command 兜底。
"""

from __future__ import annotations

from typing import Any

from ouroboros import Context  # type: ignore[import-untyped]

from ghrah.subject.runtime.ouroboros_bridge import bridge_command
from ghrah.subject.unit.base import CommandContext


async def test_none_passes_through_to_next_handler() -> None:
    """首个 handler 返回 None（不是我的）→ 穿透给下一个注册者。"""
    async with Context() as ctx:
        calls: list[str] = []

        def first(payload: dict[str, Any]) -> None:
            calls.append("first")

        def second(payload: dict[str, Any]) -> dict[str, Any]:
            calls.append("second")
            return {"success": True, "data": "claimed"}

        ctx.on("command/defended", first)
        ctx.on("command/defended", second)

        result = await bridge_command(ctx, "defended", {})
        assert calls == ["first", "second"]
        assert result == {"success": True, "data": "claimed"}


async def test_all_none_yields_unknown_command() -> None:
    """全部 handler 返回 None → Unknown command 兜底（对齐旧 dispatcher 文案）。"""
    async with Context() as ctx:

        def unclaimed(payload: dict[str, Any]) -> None:
            return None

        ctx.on("command/unclaimed", unclaimed)

        result = await bridge_command(ctx, "unclaimed", {})
        assert result == {"success": False, "error": "Unknown command: unclaimed"}


async def test_no_handler_yields_unknown_command() -> None:
    """零注册者（ctx.serial 返回 None）→ 同兜底。"""
    async with Context() as ctx:
        result = await bridge_command(ctx, "nothing", {})
        assert result == {"success": False, "error": "Unknown command: nothing"}


async def test_non_dict_result_yields_unexpected_error() -> None:
    """handler 返回非 dict 非 None → Unexpected 兜底（防御性）。"""
    async with Context() as ctx:

        def weird(payload: dict[str, Any]) -> Any:
            return "not-a-dict"

        ctx.on("command/weird", weird)

        result = await bridge_command(ctx, "weird", {})
        assert result["success"] is False
        assert "Unexpected command result" in result["error"]


async def test_cmd_ctx_placeholder_is_not_forwarded() -> None:
    """cmd_ctx 占位不透传（listener 单参签名，request_id 由装配层注 payload）。"""
    async with Context() as ctx:
        seen: list[Any] = []

        def handler(payload: dict[str, Any]) -> dict[str, Any]:
            seen.append(payload)
            return {"success": True}

        ctx.on("command/ctx-check", handler)

        result = await bridge_command(ctx, "ctx-check", {}, CommandContext.internal())
        assert result == {"success": True}
        assert seen == [{}]
