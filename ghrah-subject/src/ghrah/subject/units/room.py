# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Room built-in Subject unit（范式对齐 TaskUnit）。"""

from __future__ import annotations

from typing import Any

from ghrah.protocol.types import SendMessagePayload
from ghrah.subject.config import SubjectConfig
from ghrah.subject.project.scoped_stores import ProjectScopedRoomStore
from ghrah.subject.room.manager import RoomManager
from ghrah.subject.runtime.service_keys import (
    CORE_CLUSTER_REGISTRY,
    PROJECT_MANAGER,
    ROOM_MANAGER,
    ROOM_STORE,
)
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import ROOM_COMMANDS

__all__ = ["RoomUnit"]


class RoomUnit(SubjectUnit):
    """Owns RoomStore + RoomManager and room command/event routes.

    requires ``PROJECT_MANAGER`` 与 ``CORE_CLUSTER_REGISTRY``。Room 投递先由
    room.project_id 将稳定 agent_id 解析到 cluster，再直达该 CoreUnitHandle；
    不使用宿主全局 ``command/send_message``，因此同名 agent 不会跨 cluster 串线。
    """

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ctx: Any | None = None
        self._store: ProjectScopedRoomStore | None = None
        self._manager: RoomManager | None = None
        self._project_manager: Any | None = None
        self._meta = UnitMeta(
            name="room",
            requires=frozenset({PROJECT_MANAGER, CORE_CLUSTER_REGISTRY}),
            provides=frozenset({ROOM_MANAGER, ROOM_STORE}),
            routes=RouteSpec(commands=ROOM_COMMANDS),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> RoomManager:
        if self._manager is None:
            raise RuntimeError("RoomUnit has not been initialized.")
        return self._manager

    async def init(self, ctx: Any) -> None:
        self._ctx = ctx
        project_manager = ctx.get(PROJECT_MANAGER.name)
        self._project_manager = project_manager
        cluster_registry = ctx.get(CORE_CLUSTER_REGISTRY.name)

        async def project_roots() -> dict[str, str]:
            result = await project_manager.handle_command("project_list", {})
            projects = (result.get("data") or {}).get("projects", [])
            return {
                p["project_id"]: p["project_root_locator"]
                for p in projects
                if p.get("project_root_locator")
            }

        self._store = ProjectScopedRoomStore(
            self._config.persistence.db_path, project_roots
        )

        async def project_exists(project_id: str) -> bool:
            result = await project_manager.handle_command(
                "project_get", {"project_id": project_id}
            )
            return bool(result.get("success"))

        async def deliver(
            target: str, sender: str, content: str, room_id: str
        ) -> dict[str, Any]:
            """按 room.project_id + agent_id 找 cluster，并直达对应 CoreUnit。"""
            if self._store is None:
                return {"success": False, "data": None, "error": "RoomUnit not initialized"}
            room = await self._store.get(room_id)
            if room is None:
                return {"success": False, "data": None, "error": f"room not found: {room_id}"}
            project_result = await project_manager.handle_command(
                "project_get", {"project_id": room.project_id}
            )
            if not project_result.get("success"):
                return {
                    "success": False,
                    "data": None,
                    "error": f"project not found for room: {room.project_id}",
                }
            project = (project_result.get("data") or {}).get("project") or {}
            agents = project.get("agents") or []
            matches = [a for a in agents if a.get("agent_id") == target]
            if not matches:
                # 旧 Room 成员仍可能保存 name；只在 project 内唯一时兼容。
                matches = [a for a in agents if a.get("name") == target]
            resolved: list[tuple[dict[str, Any], Any]] = []
            for agent in matches:
                cluster_id = str(agent.get("cluster_id") or "")
                handle = await cluster_registry.ensure_cluster(
                    cluster_id,
                    project_root_locator=str(project.get("project_root_locator") or ""),
                )
                resolved.append((agent, handle))

            # 兼容旧的直接 Core spawn（ephemeral，不在 ProjectRecord.agents）：
            # 仅在本 project 的 cluster 集合内发现唯一目标时允许投递。
            if not resolved:
                for cluster_id in project.get("cluster_ids") or []:
                    handle = await cluster_registry.ensure_cluster(
                        str(cluster_id),
                        project_root_locator=str(project.get("project_root_locator") or ""),
                    )
                    for running in await handle.list_agents():
                        if running.get("agent_id") == target or running.get("name") == target:
                            resolved.append(
                                (
                                    {
                                        "agent_id": running.get("agent_id") or target,
                                        "name": running.get("name") or target,
                                        "cluster_id": cluster_id,
                                    },
                                    handle,
                                )
                            )
            if len(resolved) != 1:
                reason = "ambiguous" if resolved else "not found"
                return {
                    "success": False,
                    "data": None,
                    "error": f"agent {reason} in room project: {target}",
                }
            agent, handle = resolved[0]
            return await handle.send_message(
                SendMessagePayload(
                    target=str(agent["name"]),
                    content=content,
                    sender=sender,
                    metadata={
                        "room_id": room_id,
                        "project_id": room.project_id,
                        "agent_id": str(agent.get("agent_id") or target),
                    },
                )
            )

        self._manager = RoomManager(
            self._store,
            on_event=self._emit_event,
            project_exists=project_exists,
            deliver=deliver,
        )
        ctx.provide(ROOM_MANAGER.name, self._manager)
        ctx.provide(ROOM_STORE.name, self._store)

    async def start(self) -> None:
        if self._store is not None:
            await self._store.start()
            await self._store.migrate_all()

    async def stop(self) -> None:
        if self._store is not None:
            await self._store.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        normalized = await self._normalize_agent_identity(command, payload)
        if isinstance(normalized, dict) and normalized.get("success") is False:
            return normalized
        return await self.service.handle_command(command, normalized)

    async def _normalize_agent_identity(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """把 Room 边界的 Agent 显示名归一为 project-scoped agent_id。"""
        if self._store is None or self._project_manager is None:
            return payload
        room_id = str(payload.get("room_id") or "")
        if not room_id or command not in {"room_join", "room_leave", "room_send"}:
            return payload
        room = await self._store.get(room_id)
        if room is None:
            return payload

        def member_identity(value: str) -> tuple[str, str] | None:
            matches = [
                member
                for member in room.members
                if member.subject == value or member.subject_name == value
            ]
            if len(matches) == 1:
                member = matches[0]
                return member.subject, member.subject_name
            return None

        normalized = dict(payload)
        if command == "room_join" and str(payload.get("subject_type")) == "agent":
            project_result = await self._project_manager.handle_command(
                "project_get", {"project_id": room.project_id}
            )
            project = (project_result.get("data") or {}).get("project") or {}
            value = str(payload.get("subject") or "")
            matches = [
                agent
                for agent in project.get("agents") or []
                if agent.get("agent_id") == value or agent.get("name") == value
            ]
            if len(matches) > 1:
                return {
                    "success": False,
                    "data": None,
                    "error": f"ambiguous agent in room project: {value}",
                }
            if len(matches) == 1 and matches[0].get("agent_id"):
                normalized["subject"] = matches[0]["agent_id"]
                normalized["subject_name"] = matches[0]["name"]
            return normalized

        if command == "room_leave":
            resolved = member_identity(str(payload.get("subject") or ""))
            if resolved is not None:
                normalized["subject"] = resolved[0]
            return normalized

        if command == "room_send" and str(payload.get("author_type")) == "agent":
            resolved = member_identity(str(payload.get("author") or ""))
            if resolved is not None:
                normalized["author"] = resolved[0]

        if command == "room_send":
            data = dict(payload.get("data") or {})
            targets = data.get("targets")
            if isinstance(targets, list):
                normalized_targets: list[str] = []
                for target in targets:
                    resolved = member_identity(str(target))
                    normalized_targets.append(resolved[0] if resolved else str(target))
                data["targets"] = normalized_targets
                normalized["data"] = data
        return normalized

    async def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """RoomManager 的 ``on_event`` 回调：保留 async 签名，体内同步 ctx.emit。"""

        ctx = self._ctx
        if ctx is None:
            return
        ctx.emit(f"event/{event_type}", payload)
