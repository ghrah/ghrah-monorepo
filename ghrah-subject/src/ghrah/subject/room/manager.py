# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""RoomManager：Room 命令编排层（10 命令 + seq 单点分配 + send 收敛点）。

范式对齐 task/manager.TaskManager：``_HANDLERS`` 表 + ``_ok/_err`` +
ValidationError 收窄；纯 store + 回调，不依赖 SubjectContext，便于独立单测。

send 双路径收敛（Room 计划附录）：协议面（human/Mock ``room_send`` 命令）与
实现面（agent 经 Core send ability → ``ctx.serial("command/room_send")``）
都汇入 ``append_log``——分配 seq、落库、广播 ROOM_LOG_APPENDED。

human 消息投递（投递回路补全）：``room_send``（author_type=human）落账后，
经注入的 ``deliver`` 回调（RoomUnit 接线 ``ctx.serial("command/send_message")``
→ CoreUnit → Supervisor.send）把消息送达 room 内 agent 成员。投递为
fire-and-forget：不阻塞回执、失败不重试、落账仍为权威；author_type=agent
不投递（作者即发送者，agent 回复由其对端 send ability 走 Supervisor 投递）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from ghrah.protocol.types import (
    RoomCreatePayload,
    RoomDeletePayload,
    RoomGetLogPayload,
    RoomJoinPayload,
    RoomLeavePayload,
    RoomListPayload,
    RoomSendPayload,
    RoomSubjectType,
    RoomUpdatePayload,
)
from ghrah.subject.room.models import (
    RoomLogRecord,
    RoomRecord,
    make_room_log_record,
    make_room_member,
    make_room_record,
    now_iso,
)
from ghrah.subject.room.store import ConcurrentModificationError, RoomStore

logger = logging.getLogger(__name__)

OnEvent = Callable[[str, dict[str, Any]], Awaitable[None]]
ProjectExists = Callable[[str], Awaitable[bool]]
Deliver = Callable[[str, str, str, str], Awaitable[dict[str, Any]]]
"""deliver(target, sender, content, room_id) → command_result。

room_id 随投递写入消息 metadata（AgentMessage.metadata.room_id）→ 链节点
messages_delta，供回复归属推导（Room Filter）消费。
"""

__all__ = ["RoomManager"]


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict[str, Any]:
    return {"success": False, "data": None, "error": msg}


class RoomManager:
    """Room 命令编排：CRUD + 成员多对多 + seq 单点分配 + send 解析收敛。"""

    def __init__(
        self,
        store: RoomStore,
        *,
        on_event: OnEvent | None = None,
        project_exists: ProjectExists | None = None,
        deliver: Deliver | None = None,
    ) -> None:
        self._store = store
        self._on_event = on_event
        self._project_exists = project_exists
        self._deliver = deliver

    @property
    def store(self) -> RoomStore:
        return self._store

    async def handle_command(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        handler = _HANDLERS.get(command)
        if handler is None:
            return _err(f"unknown command: {command}")
        try:
            return await handler(self, payload)
        except ValidationError as e:
            missing = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]
            if missing:
                return _err(f"{missing[0]} required")
            return _err(f"invalid payload: {e}")

    # ─── helpers ───

    async def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        await self._on_event(event_type, payload)

    async def _emit_room(self, event_type: str, room: RoomRecord) -> None:
        await self._emit(event_type, {"room": room.to_wire()})

    async def _require_room(self, room_id: str) -> RoomRecord | dict[str, Any]:
        room = await self._store.get(room_id)
        if room is None:
            return _err(f"room not found: {room_id}")
        return room

    # ─── 命令 handlers ───

    async def _handle_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomCreatePayload.model_validate(payload)
        name = p.name.strip()
        if not name:
            return _err("name required")
        if self._project_exists is not None and not await self._project_exists(
            p.project_id
        ):
            return _err(f"project not found: {p.project_id}")
        record = make_room_record(project_id=p.project_id, name=name)
        await self._store.upsert(record)
        await self._emit_room("room_created", record)
        return _ok({"room": record.to_wire()})

    async def _handle_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomListPayload.model_validate(payload)
        records = await self._store.list(
            project_id=p.project_id,
            status=p.status.value if p.status is not None else None,
        )
        rooms = [r.to_wire() for r in records]
        return _ok({"rooms": rooms, "count": len(rooms)})

    async def _handle_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        room_id = payload.get("room_id", "")
        existing = await self._require_room(room_id)
        if isinstance(existing, dict):
            return existing
        return _ok({"room": existing.to_wire()})

    async def _handle_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomUpdatePayload.model_validate(payload)

        def mutator(r: RoomRecord) -> RoomRecord:
            updates: dict[str, Any] = {"updated_at": now_iso()}
            if p.name is not None:
                updates["name"] = p.name
            return r.model_copy(update=updates)

        try:
            updated = await self._store.update(
                p.room_id, expected_version=p.expected_version, mutator=mutator
            )
        except ConcurrentModificationError:
            return _err(
                f"version conflict: expected {p.expected_version}"
            )
        if updated is None:
            return _err(f"room not found: {p.room_id}")
        await self._emit_room("room_updated", updated)
        return _ok({"room": updated.to_wire()})

    async def _handle_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomDeletePayload.model_validate(payload)
        existing = await self._require_room(p.room_id)
        if isinstance(existing, dict):
            return existing
        if not p.force:
            log_count = await self._store.count_logs(p.room_id)
            if log_count > 0:
                return _err(
                    f"room has {log_count} log entries; pass force=true to delete"
                )
        await self._store.delete(p.room_id)
        await self._emit(
            "room_deleted",
            {"room_id": existing.room_id, "project_id": existing.project_id},
        )
        return _ok(
            {"room_id": existing.room_id, "project_id": existing.project_id}
        )

    async def _handle_join(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomJoinPayload.model_validate(payload)
        if not p.subject.strip():
            return _err("subject required")
        existing = await self._require_room(p.room_id)
        if isinstance(existing, dict):
            return existing
        if any(m.subject == p.subject for m in existing.members):
            # 幂等 join：已在 room → 成功返回，不发事件（对齐 mock 契约）
            return _ok({"room": existing.to_wire()})

        member = make_room_member(p.subject, p.subject_type, p.subject_name)

        def mutator(r: RoomRecord) -> RoomRecord:
            return r.model_copy(
                update={"members": [*r.members, member], "updated_at": now_iso()}
            )

        updated = await self._store.update(
            p.room_id, expected_version=None, mutator=mutator
        )
        if updated is None:
            return _err(f"room not found: {p.room_id}")
        await self._emit(
            "room_member_joined",
            {"room": updated.to_wire(), "member": member.model_dump(mode="json")},
        )
        return _ok({"room": updated.to_wire()})

    async def _handle_leave(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomLeavePayload.model_validate(payload)
        existing = await self._require_room(p.room_id)
        if isinstance(existing, dict):
            return existing
        if not any(m.subject == p.subject for m in existing.members):
            return _err(f"subject not in room: {p.subject}")

        def mutator(r: RoomRecord) -> RoomRecord:
            return r.model_copy(
                update={
                    "members": [m for m in r.members if m.subject != p.subject],
                    "updated_at": now_iso(),
                }
            )

        updated = await self._store.update(
            p.room_id, expected_version=None, mutator=mutator
        )
        if updated is None:
            return _err(f"room not found: {p.room_id}")
        await self._emit(
            "room_member_left",
            {"room": updated.to_wire(), "subject": p.subject},
        )
        return _ok({"room": updated.to_wire()})

    async def _handle_get_members(self, payload: dict[str, Any]) -> dict[str, Any]:
        room_id = payload.get("room_id", "")
        existing = await self._require_room(room_id)
        if isinstance(existing, dict):
            return existing
        members = [m.model_dump(mode="json") for m in existing.members]
        return _ok(
            {"room_id": existing.room_id, "members": members, "count": len(members)}
        )

    async def _handle_get_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomGetLogPayload.model_validate(payload)
        existing = await self._require_room(p.room_id)
        if isinstance(existing, dict):
            return existing
        records = await self._store.get_log(
            p.room_id, since_seq=p.since_seq, limit=p.limit
        )
        entries = [r.to_wire() for r in records]
        return _ok(
            {"room_id": p.room_id, "entries": entries, "count": len(entries)}
        )

    async def _handle_send(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = RoomSendPayload.model_validate(payload)
        room = await self._store.get(p.room_id)
        if room is None:
            return _err(f"room not found: {p.room_id}")
        # 写时校验：author 合法 = human 或 room 成员 agent（附录契约）
        if p.author_type == RoomSubjectType.AGENT and not any(
            m.subject == p.author for m in room.members
        ):
            return _err(f"author not in room: {p.author}")
        # data.targets（若给）⊆ room 的 agent 成员（{message, targets?} 约定）
        error = self._validate_targets(room, p.data.get("targets"))
        if error is not None:
            return _err(error)
        result = await self.append_log(
            p.room_id, author=p.author, author_type=p.author_type, data=p.data
        )
        if result.get("success") and p.author_type == RoomSubjectType.HUMAN:
            self._schedule_delivery(room, p)
        return result

    def _schedule_delivery(self, room: RoomRecord, p: RoomSendPayload) -> None:
        """human 消息落账成功后 fire-and-forget 投递给 room 内 agent。

        投递对象：data.targets（已校验 ⊆ agent 成员）优先；缺省整室 agent
        成员；恒排除作者。不阻塞 room_send 回执，失败仅记日志不重试。
        """
        if self._deliver is None:
            return
        message = p.data.get("message")
        if not isinstance(message, str) or not message:
            logger.warning(
                "room_send: skip delivery (no message) room=%s author=%s",
                p.room_id,
                p.author,
            )
            return
        targets = self._resolve_delivery_targets(room, p)
        for target in targets:
            try:
                asyncio.get_running_loop().create_task(
                    self._deliver_one(target, p.room_id, sender=p.author, content=message)
                )
            except RuntimeError:
                logger.warning(
                    "room_send: no running loop, delivery skipped room=%s target=%s",
                    p.room_id,
                    target,
                )

    @staticmethod
    def _resolve_delivery_targets(room: RoomRecord, p: RoomSendPayload) -> list[str]:
        data_targets = p.data.get("targets")
        agent_members = [
            m.subject for m in room.members if m.subject_type == RoomSubjectType.AGENT
        ]
        if isinstance(data_targets, list) and data_targets:
            member_set = set(agent_members)
            targets = [t for t in data_targets if t in member_set]
        else:
            targets = list(agent_members)
        return [t for t in targets if t != p.author]

    async def _deliver_one(
        self, target: str, room_id: str, *, sender: str, content: str
    ) -> None:
        try:
            result = await self._deliver(target, sender, content, room_id)  # type: ignore[misc]
        except Exception:
            logger.exception(
                "room delivery failed: target=%s sender=%s", target, sender
            )
            return
        if not result.get("success"):
            logger.warning(
                "room delivery rejected: target=%s sender=%s error=%s",
                target,
                sender,
                result.get("error"),
            )

    @staticmethod
    def _validate_targets(room: RoomRecord, targets: Any) -> str | None:
        if targets is None:
            return None
        if not isinstance(targets, list) or not all(
            isinstance(t, str) for t in targets
        ):
            return "invalid targets: expected string[]"
        agent_members = {
            m.subject for m in room.members if m.subject_type == RoomSubjectType.AGENT
        }
        for t in targets:
            if t not in agent_members:
                return f"target not in room: {t}"
        return None

    # ─── send 收敛点（双路径共用：room_send 命令 + Core send ability serial） ───

    async def append_log(
        self,
        room_id: str,
        *,
        author: str,
        author_type: RoomSubjectType,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """分配 seq → 落库 → 广播 ROOM_LOG_APPENDED → 返回 _ok({entry})。"""
        result = await self._store.append_log(
            room_id,
            lambda seq: make_room_log_record(
                room_id=room_id,
                seq=seq,
                author=author,
                author_type=author_type,
                data=data,
            ),
        )
        if result is None:
            return _err(f"room not found: {room_id}")
        record: RoomLogRecord = result[0]
        await self._emit("room_log_appended", {"entry": record.to_wire()})
        return _ok({"entry": record.to_wire()})

    # ─── send ability 支撑（Core 侧 recipients 解析用） ───

    async def resolve_recipients(
        self, room_ids: list[str], extra_targets: list[str] | None = None
    ) -> dict[str, Any]:
        """recipients = Σ room 的 agent 成员 ∪ targets 去重。

        任一 room 不存在 → _err；返回 _ok({recipients, rooms})（rooms 为
        校验通过的 room wire 列表，供调用方逐 room 落账）。
        """
        recipients: list[str] = []
        seen: set[str] = set()
        rooms: list[dict[str, Any]] = []
        for room_id in room_ids:
            room = await self._store.get(room_id)
            if room is None:
                return _err(f"room not found: {room_id}")
            rooms.append(room.to_wire())
            for m in room.members:
                if m.subject_type == RoomSubjectType.AGENT and m.subject not in seen:
                    seen.add(m.subject)
                    recipients.append(m.subject)
        for t in extra_targets or []:
            if t not in seen:
                seen.add(t)
                recipients.append(t)
        return _ok({"recipients": recipients, "rooms": rooms})


_HANDLERS: dict[str, Callable[[RoomManager, dict[str, Any]], Any]] = {
    "room_create": RoomManager._handle_create,
    "room_list": RoomManager._handle_list,
    "room_get": RoomManager._handle_get,
    "room_update": RoomManager._handle_update,
    "room_delete": RoomManager._handle_delete,
    "room_join": RoomManager._handle_join,
    "room_leave": RoomManager._handle_leave,
    "room_get_members": RoomManager._handle_get_members,
    "room_get_log": RoomManager._handle_get_log,
    "room_send": RoomManager._handle_send,
}
