# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""PluginSession unit：协商双重触发。

- 连接级：``plugin_negotiate`` 命令 responder（Observer → Subject），回执
  ``command_result.data`` = negotiator 纯函数输出；
- 变更级：装配/卸载/崩溃后广播 ``plugin_negotiated``（纯重协商信号，携带
  变更涉及的 plugin_id 清单）。

两路共用 ``negotiate`` 纯函数（零状态分歧）。``plugin_negotiate`` 是插件
机制自身命令：走 builtin 式注册 + owner 表登记（非 exclusive）。

协商真相源是装配链持有的 ``PluginSessionState``（已挂载 spec 集）；本
unit 只读快照 + 广播，不持有插件状态。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ghrah.protocol.payloads.plugin import (
    PluginNegotiatedPayload,
    PluginNegotiatePayload,
)

from ghrah.subject.runtime.service_keys import OBSERVER_EVENT_BUS, SubjectServiceKey
from ghrah.subject.unit.base import RouteSpec, SubjectUnit, UnitMeta

if TYPE_CHECKING:
    from ouroboros import Context  # type: ignore[import-untyped]

    from ghrah.subject.runtime.plugin_mount import PluginSessionState

__all__ = ["PLUGIN_SESSION_SERVICE", "PluginSession"]

logger = logging.getLogger(__name__)

PLUGIN_SESSION_SERVICE = SubjectServiceKey["PluginSession"]("plugin_session_service")


class PluginSession(SubjectUnit):
    """插件协商会话 unit（挂载名 ``plugin_session``）。

    Attributes:
        state: 装配链注入的会话状态（已挂载 spec 集快照源）。
    """

    def __init__(self, state: PluginSessionState) -> None:
        self._meta = UnitMeta(
            name="plugin_session",
            routes=RouteSpec(commands=frozenset({"plugin_negotiate"})),
        )
        self._state = state
        self._ctx: Context | None = None

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def state(self) -> PluginSessionState:
        return self._state

    async def init(self, ctx: Any) -> None:
        self._ctx = ctx
        ctx.provide(PLUGIN_SESSION_SERVICE.name, self)

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: Any,
    ) -> dict[str, Any]:
        if command != "plugin_negotiate":
            return {"success": False, "error": f"Unknown command: {command}"}
        try:
            parsed = PluginNegotiatePayload.model_validate(payload)
        except Exception as exc:
            return {"success": False, "error": f"invalid plugin_negotiate payload: {exc}"}
        result = self._state.negotiate(ts=parsed.enabled_ts)
        return {"success": True, "data": result.model_dump()}

    async def publish_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """经 Observer 事件总线广播插件域事件（bus 不在场时日志降级）。"""
        if self._ctx is None:
            return
        bus = self._ctx.get(OBSERVER_EVENT_BUS.name, strict=False)
        if bus is None:
            logger.debug("plugin event '%s' skipped: no observer event bus mounted.", event_type)
            return
        await bus.publish(event_type, payload)

    async def broadcast_negotiated(self, changed: list[str]) -> None:
        """广播 ``plugin_negotiated``（变更级重协商信号）。"""
        await self.publish_event(
            "plugin_negotiated",
            PluginNegotiatedPayload(changed=changed).model_dump(),
        )
