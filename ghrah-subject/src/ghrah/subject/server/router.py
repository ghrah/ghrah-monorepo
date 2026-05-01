"""Observer 命令路由器。

解析 Observer WebSocket 消息类型，路由到对应的处理器。

路由规则：
    - agent_management_commands (spawn_agent, etc.) → 转发到 Core（通过回调）
    - workspace_commands → 本地处理器回调
    - manifest_commands → 本地处理器回调
    - hitl_response → 本地处理器回调
    - subscribe/unsubscribe → 本地 ConnectionManager
    - persist_commands → 本地处理器回调（Core → Subject 方向）
    - execute_ability → 本地处理器回调（Core → Subject 方向）
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from ghrah.protocol.types import (
    CORE_COMMANDS,
    MANIFEST_COMMANDS,
    PERSIST_COMMANDS,
    WORKSPACE_COMMANDS,
    CommandType,
    EventType,
    Message,
    create_command_result,
    create_error,
    generate_request_id,
)
from ghrah.subject.server.connection_manager import ConnectionManager
from ghrah.subject.server.event_bus import EventBus

logger = logging.getLogger(__name__)

CommandHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]
CoreForwardHandler = Callable[[str, dict[str, Any], str | None], Coroutine[Any, Any, dict[str, Any]]]
EventCallback = Callable[[Message], Coroutine[Any, Any, None]]


class ObserverRouter:
    """Observer 消息路由器。

    将 Observer 发来的命令消息路由到对应的处理器。
    通过回调机制与 SubjectService 解耦，SubjectService 在集成时
    注册各类型命令的处理器。

    回调类型：
        - core_forward_handler: Agent 管理命令转发到 Core 的回调
          签名: (msg_type: str, payload: dict, request_id: str | None) -> dict
        - workspace_handler: workspace_* 命令的本地处理器
          签名: (command: str, payload: dict) -> dict
        - manifest_handler: manifest_* 命令的本地处理器
          签名: (command: str, payload: dict) -> dict
        - hitl_response_handler: hitl_response 的本地处理器
          签名: (payload: dict) -> None
        - persist_handler: persist_* 命令的本地处理器
          签名: (command: str, payload: dict) -> dict
        - ability_handler: execute_ability 的本地处理器
          签名: (payload: dict) -> dict
    """

    def __init__(
        self,
        connection_manager: ConnectionManager,
        event_bus: EventBus,
        *,
        core_forward_handler: CoreForwardHandler | None = None,
        workspace_handler: CommandHandler | None = None,
        manifest_handler: CommandHandler | None = None,
        hitl_response_handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        persist_handler: CommandHandler | None = None,
        ability_handler: CommandHandler | None = None,
    ) -> None:
        self._connection_manager = connection_manager
        self._event_bus = event_bus
        self._core_forward_handler = core_forward_handler
        self._workspace_handler = workspace_handler
        self._manifest_handler = manifest_handler
        self._hitl_response_handler = hitl_response_handler
        self._persist_handler = persist_handler
        self._ability_handler = ability_handler

    async def handle_command(
        self,
        message: Message,
        session_id: str,
    ) -> Message | None:
        """处理来自 Observer 的命令消息。

        Args:
            message: 收到的 WebSocket 消息
            session_id: 发送者的 session ID

        Returns:
            命令执行结果消息，或 None（subscribe/unsubscribe 已本地处理）
        """
        request_id = message.request_id or generate_request_id()

        # HITL 响应：本地处理
        if message.type == CommandType.HITL_RESPONSE.value:
            return await self._handle_hitl_response(message, session_id, request_id)

        # 订阅/取消订阅：本地处理
        if message.type == CommandType.SUBSCRIBE.value:
            return await self._handle_subscribe(message, session_id, request_id)

        if message.type == CommandType.UNSUBSCRIBE.value:
            return await self._handle_unsubscribe(message, session_id, request_id)

        # Agent 管理命令：转发到 Core
        if message.type in CORE_COMMANDS:
            return await self._handle_core_forward(message, session_id, request_id)

        # Workspace 命令：本地处理
        if message.type in WORKSPACE_COMMANDS:
            return await self._handle_workspace(message, session_id, request_id)

        # Manifest 命令：本地处理
        if message.type in MANIFEST_COMMANDS:
            return await self._handle_manifest(message, session_id, request_id)

        # 持久化命令：本地处理（Core → Subject 方向，但 Observer 可能请求）
        if message.type in PERSIST_COMMANDS:
            return await self._handle_persist(message, session_id, request_id)

        # Execute ability：本地处理
        if message.type == CommandType.EXECUTE_ABILITY.value:
            return await self._handle_ability(message, session_id, request_id)

        return create_error(
            code="UNKNOWN_COMMAND",
            message=f"Unknown command type: {message.type}",
            request_id=request_id,
        )

    async def handle_event(
        self,
        message: Message,
        session_id: str,
    ) -> None:
        """处理事件消息，发布到 EventBus。"""
        try:
            event_type = EventType(message.type)
        except ValueError:
            logger.warning(f"Unknown event type: {message.type}")
            return

        logger.info(
            "handle_event: event_type=%s session_id=%s agent=%s publishing via EventBus",
            event_type.value, session_id,
            message.payload.get("agent_name", ""),
        )
        await self._event_bus.publish(message)

    # ─── 本地处理 ───

    async def _handle_subscribe(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        from ghrah.protocol.types import SubscribePayload

        payload = SubscribePayload(**message.payload)
        self._connection_manager.subscribe(
            session_id=session_id,
            agent_names=payload.agent_names,
            event_types=payload.event_types,
        )
        sub_info = self._connection_manager.get_subscription_info(session_id)
        return create_command_result(
            request_id=request_id,
            success=True,
            data=sub_info,
        )

    async def _handle_unsubscribe(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        from ghrah.protocol.types import UnsubscribePayload

        payload = UnsubscribePayload(**message.payload)
        self._connection_manager.unsubscribe(
            session_id=session_id,
            agent_names=payload.agent_names,
            event_types=payload.event_types,
        )
        sub_info = self._connection_manager.get_subscription_info(session_id)
        return create_command_result(
            request_id=request_id,
            success=True,
            data=sub_info,
        )

    async def _handle_hitl_response(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        """处理 HITL 响应：委托给本地回调。"""
        if self._hitl_response_handler is None:
            return create_command_result(
                request_id=request_id,
                success=False,
                error="HITL response handler not configured",
            )

        try:
            await self._hitl_response_handler(message.payload)
            return create_command_result(
                request_id=request_id,
                success=True,
                data={"processed": True},
            )
        except Exception as e:
            logger.error(f"Error handling hitl_response: {e}")
            return create_command_result(
                request_id=request_id,
                success=False,
                error=str(e),
            )

    async def _handle_core_forward(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        """Agent 管理命令：通过回调转发到 Core。"""
        if self._core_forward_handler is None:
            return create_command_result(
                request_id=request_id,
                success=False,
                error="Core forward handler not configured",
            )

        try:
            result = await self._core_forward_handler(
                message.type, message.payload, request_id
            )
            return create_command_result(
                request_id=request_id,
                success=result.get("success", True),
                data=result.get("data"),
                error=result.get("error"),
            )
        except Exception as e:
            logger.error(f"Error forwarding command to Core: {e}")
            return create_command_result(
                request_id=request_id,
                success=False,
                error=str(e),
            )

    async def _handle_workspace(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        """Workspace 命令：本地处理。"""
        if self._workspace_handler is None:
            return create_command_result(
                request_id=request_id,
                success=False,
                error="Workspace handler not configured",
            )

        try:
            result = await self._workspace_handler(message.type, message.payload)
            return create_command_result(
                request_id=request_id,
                success=result.get("success", True),
                data=result.get("data"),
                error=result.get("error"),
            )
        except Exception as e:
            logger.error(f"Error handling workspace command: {e}")
            return create_command_result(
                request_id=request_id,
                success=False,
                error=str(e),
            )

    async def _handle_manifest(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        """Manifest 命令：本地处理。"""
        if self._manifest_handler is None:
            return create_command_result(
                request_id=request_id,
                success=False,
                error="Manifest handler not configured",
            )

        try:
            result = await self._manifest_handler(message.type, message.payload)
            return create_command_result(
                request_id=request_id,
                success=result.get("success", True),
                data=result.get("data"),
                error=result.get("error"),
            )
        except Exception as e:
            logger.error(f"Error handling manifest command: {e}")
            return create_command_result(
                request_id=request_id,
                success=False,
                error=str(e),
            )

    async def _handle_persist(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        """持久化命令：本地处理。"""
        if self._persist_handler is None:
            return create_command_result(
                request_id=request_id,
                success=False,
                error="Persist handler not configured",
            )

        try:
            result = await self._persist_handler(message.type, message.payload)
            return create_command_result(
                request_id=request_id,
                success=result.get("success", True),
                data=result.get("data"),
                error=result.get("error"),
            )
        except Exception as e:
            logger.error(f"Error handling persist command: {e}")
            return create_command_result(
                request_id=request_id,
                success=False,
                error=str(e),
            )

    async def _handle_ability(
        self, message: Message, session_id: str, request_id: str
    ) -> Message:
        """execute_ability 命令：本地处理。"""
        if self._ability_handler is None:
            return create_command_result(
                request_id=request_id,
                success=False,
                error="Ability handler not configured",
            )

        try:
            result = await self._ability_handler(message.type, message.payload)
            return create_command_result(
                request_id=request_id,
                success=result.get("success", True),
                data=result.get("data"),
                error=result.get("error"),
            )
        except Exception as e:
            logger.error(f"Error handling execute_ability: {e}")
            return create_command_result(
                request_id=request_id,
                success=False,
                error=str(e),
            )
