"""SubjectPersistenceService：接收 Gateway 的持久化命令，委托给 SqliteBackend 执行。

这是 Core 的 RemoteBackend 的服务端。Core 通过 Gateway 发送 persist_* 命令，
Subject 的 SubjectPersistenceService 接收命令，委托给 SqliteBackend 执行实际的 SQLite I/O。

命令协议（与 RemoteBackend 一一对应）：
- persist_save_node → 保存节点
- persist_load_node → 加载节点
- persist_load_chain → 加载链
- persist_save_chain_meta → 保存链元信息
- persist_load_chain_meta → 加载链元信息
- persist_save_messages → 保存消息
- persist_load_messages → 加载消息
- persist_delete_chain → 删除链
- persist_list_agents → 列出 agents
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ghrah.context.persistence.sqlite_backend import SqliteBackend

logger = logging.getLogger(__name__)

__all__ = ["SubjectPersistenceService"]

_PERSIST_COMMANDS = frozenset({
    "persist_save_node",
    "persist_load_node",
    "persist_load_chain",
    "persist_save_chain_meta",
    "persist_load_chain_meta",
    "persist_save_messages",
    "persist_load_messages",
    "persist_delete_chain",
    "persist_list_agents",
})


class SubjectPersistenceService:
    """接收 Gateway 的持久化命令，委托给 SqliteBackend 执行。

    Usage::

        service = SubjectPersistenceService(db_path="~/.ghrah/subject.db")
        await service.start()

        result = await service.handle_command("persist_save_node", payload)
        await service.stop()
    """

    def __init__(self, db_path: str | Path = "") -> None:
        if not db_path:
            db_path = Path.home() / ".ghrah" / "subject.db"
        self._db_path = Path(db_path)
        self._backend: SqliteBackend | None = None
        self._lock = asyncio.Lock()

    @property
    def backend(self) -> SqliteBackend | None:
        return self._backend

    async def start(self) -> None:
        """启动服务：打开 SqliteBackend 连接。"""
        async with self._lock:
            if self._backend is not None:
                return
            self._backend = SqliteBackend(db_path=self._db_path)
            await self._backend.connect()
        logger.info("SubjectPersistenceService started (db=%s)", self._db_path)

    async def stop(self) -> None:
        """停止服务：关闭 SqliteBackend 连接。"""
        async with self._lock:
            backend = self._backend
            if backend is None:
                return
            self._backend = None
        await backend.close()
        logger.info("SubjectPersistenceService stopped")

    async def handle_command(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """处理来自 Gateway 的持久化命令。

        Args:
            command: 命令名称（persist_*）
            payload: 命令载荷

        Returns:
            包含 success 字段的响应字典
        """
        async with self._lock:
            backend = self._backend
        if backend is None:
            return {"success": False, "error": "PersistenceService not started"}

        if command not in _PERSIST_COMMANDS:
            return {"success": False, "error": f"Unknown command: {command}"}

        handler = _HANDLERS.get(command)
        if handler is None:
            return {"success": False, "error": f"No handler for command: {command}"}

        try:
            return await handler(backend, payload)
        except Exception as exc:
            logger.exception("Error handling command %s", command)
            return {"success": False, "error": str(exc)}


async def _handle_save_node(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    from ghrah.context.persistence.serialization import deserialize_node

    node_data = payload.get("node")
    if node_data is None:
        return {"success": False, "error": "Missing 'node' in payload"}

    node = deserialize_node(node_data)
    await backend.save_node(node)
    return {"success": True}


async def _handle_load_node(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    from ghrah.context.persistence.serialization import serialize_node

    node_id = payload.get("node_id")
    if not node_id:
        return {"success": False, "error": "Missing 'node_id' in payload"}

    node = await backend.load_node(node_id)
    if node is None:
        return {"success": True, "data": {"node": None}}

    serialized = serialize_node(node)
    return {"success": True, "data": {"node": serialized}}


async def _handle_load_chain(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    from ghrah.context.persistence.serialization import serialize_node

    agent_name = payload.get("agent_name")
    if not agent_name:
        return {"success": False, "error": "Missing 'agent_name' in payload"}

    nodes = await backend.load_chain(agent_name)
    serialized = [serialize_node(n) for n in nodes]
    return {"success": True, "data": {"nodes": serialized}}


async def _handle_save_chain_meta(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    agent_name = payload.get("agent_name")
    if not agent_name:
        return {"success": False, "error": "Missing 'agent_name' in payload"}

    branches: dict[str, str] = payload.get("branches", {})
    current_state: dict[str, Any] = payload.get("current_state", {})
    await backend.save_chain_meta(agent_name, branches, current_state)
    return {"success": True}


async def _handle_load_chain_meta(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    agent_name = payload.get("agent_name")
    if not agent_name:
        return {"success": False, "error": "Missing 'agent_name' in payload"}

    result = await backend.load_chain_meta(agent_name)
    if result is None:
        return {"success": True, "data": None}

    branches, current_state = result
    return {"success": True, "data": {"branches": branches, "current_state": current_state}}


async def _handle_save_messages(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    from ghrah.context.persistence.serialization import deserialize_messages

    agent_name = payload.get("agent_name")
    if not agent_name:
        return {"success": False, "error": "Missing 'agent_name' in payload"}

    messages_data = payload.get("messages")
    if messages_data is None:
        return {"success": False, "error": "Missing 'messages' in payload"}

    messages = deserialize_messages(messages_data)
    await backend.save_messages(agent_name, messages)
    return {"success": True}


async def _handle_load_messages(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    from ghrah.context.persistence.serialization import serialize_messages

    agent_name = payload.get("agent_name")
    if not agent_name:
        return {"success": False, "error": "Missing 'agent_name' in payload"}

    messages = await backend.load_messages(agent_name)
    serialized = serialize_messages(messages)
    return {"success": True, "data": {"messages": serialized}}


async def _handle_delete_chain(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    agent_name = payload.get("agent_name")
    if not agent_name:
        return {"success": False, "error": "Missing 'agent_name' in payload"}

    await backend.delete_chain(agent_name)
    return {"success": True}


async def _handle_list_agents(
    backend: SqliteBackend, payload: dict[str, Any]
) -> dict[str, Any]:
    agents = await backend.list_agents()
    return {"success": True, "data": {"agents": agents}}


_HANDLER_TYPE = Callable[[SqliteBackend, dict[str, Any]], Awaitable[dict[str, Any]]]

_HANDLERS: dict[str, _HANDLER_TYPE] = {
    "persist_save_node": _handle_save_node,
    "persist_load_node": _handle_load_node,
    "persist_load_chain": _handle_load_chain,
    "persist_save_chain_meta": _handle_save_chain_meta,
    "persist_load_chain_meta": _handle_load_chain_meta,
    "persist_save_messages": _handle_save_messages,
    "persist_load_messages": _handle_load_messages,
    "persist_delete_chain": _handle_delete_chain,
    "persist_list_agents": _handle_list_agents,
}
