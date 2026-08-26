# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Room 域模型：RoomRecord（元数据+成员+seq 水位）/ RoomLogRecord（append-only 日志节点）。

继承 protocol RoomInfoPayload / RoomLogEntryPayload 保证 wire 一一对应
（范式对齐 task/models.TaskRecord）。契约来源：Room 计划 §3.1 + 附录。
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from ghrah.protocol.types import (
    RoomInfoPayload,
    RoomLogEntryPayload,
    RoomMember,
    RoomStatus,
    RoomSubjectType,
)

__all__ = [
    "RoomLogRecord",
    "RoomRecord",
    "make_room_log_record",
    "make_room_record",
    "now_iso",
]


def now_iso() -> str:
    """当前 UTC ISO 时间戳（RoomRecord.created_at/updated_at/joined_at 用）。"""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class RoomRecord(RoomInfoPayload):
    """Subject 内部 Room 记录。

    与 protocol RoomInfoPayload 字段全同（含 version 乐观锁与
    seq_watermark——两者均落 wire，对齐 TS RoomInfoPayload 契约）。
    """

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RoomLogRecord(RoomLogEntryPayload):
    """Subject 内部 RoomLog 节点 = 最小信封 + 自由 map（不预置业务 schema）。"""

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def make_room_record(*, project_id: str, name: str) -> RoomRecord:
    """创建新 room：room_id 生成、status=ACTIVE、成员空、seq 水位 0。"""
    now = now_iso()
    return RoomRecord(
        room_id=uuid4().hex,
        project_id=project_id,
        name=name,
        status=RoomStatus.ACTIVE,
        members=[],
        seq_watermark=0,
        version=1,
        created_at=now,
        updated_at=now,
    )


def make_room_log_record(
    *,
    room_id: str,
    seq: int,
    author: str,
    author_type: RoomSubjectType,
    data: dict[str, Any] | None = None,
) -> RoomLogRecord:
    """构造 RoomLog 节点（seq 由 store 单点分配，此处仅组装）。"""
    return RoomLogRecord(
        id=uuid4().hex,
        room_id=room_id,
        seq=seq,
        author=author,
        author_type=author_type,
        timestamp=time.time(),
        data=dict(data) if data else {},
    )


def make_room_member(
    subject: str, subject_type: RoomSubjectType
) -> RoomMember:
    """构造新成员（joined_at = now）。"""
    return RoomMember(subject=subject, subject_type=subject_type, joined_at=now_iso())
