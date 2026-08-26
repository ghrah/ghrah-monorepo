# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Room built-in Subject unit（范式对齐 TaskUnit）。"""

from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.project.scoped_stores import ProjectScopedRoomStore
from ghrah.subject.room.manager import RoomManager
from ghrah.subject.runtime.service_keys import PROJECT_MANAGER, ROOM_MANAGER, ROOM_STORE
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import ROOM_COMMANDS

__all__ = ["RoomUnit"]


class RoomUnit(SubjectUnit):
    """Owns RoomStore + RoomManager and room command/event routes.

    requires ``PROJECT_MANAGER``（room.project_id 存在性校验）。装配顺序：
    subject 单元在前、CoreUnit 经 registry 懒挂载在后——本单元在 ProjectUnit
    之后挂载即满足「RoomUnit 先于 CoreUnit」（send 回路唯一跨 unit 耦合点，
    见 Room 计划附录）。
    """

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ctx: Any | None = None
        self._store: ProjectScopedRoomStore | None = None
        self._manager: RoomManager | None = None
        self._meta = UnitMeta(
            name="room",
            requires=frozenset({PROJECT_MANAGER}),
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
            """human 消息投递：经宿主 serial 命令面 → CoreUnit send_message
            （Supervisor.send）送达 agent。room_id 随 metadata 透传 → 链节点
            messages_delta（回复归属推导用）。CoreUnit 未挂载时 serial 返回
            None，按 Unknown command 语义返回失败（投递侧仅记日志）。"""
            if self._ctx is None:
                return {"success": False, "data": None, "error": "RoomUnit not initialized"}
            result = await self._ctx.serial(
                "command/send_message",
                {
                    "target": target,
                    "content": content,
                    "sender": sender,
                    "metadata": {"room_id": room_id},
                },
            )
            if not isinstance(result, dict):
                return {
                    "success": False,
                    "data": None,
                    "error": "Unknown command: send_message (core unit not mounted?)",
                }
            return result

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
        return await self.service.handle_command(command, payload)

    async def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """RoomManager 的 ``on_event`` 回调：保留 async 签名，体内同步 ctx.emit。"""

        ctx = self._ctx
        if ctx is None:
            return
        ctx.emit(f"event/{event_type}", payload)
