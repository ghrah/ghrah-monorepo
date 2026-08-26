# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""RoomStore 单测：CRUD / 乐观锁 / seq 单点分配 / append-only 日志 / 级联删除。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghrah.subject.room.models import (
    RoomRecord,
    make_room_log_record,
    make_room_record,
)
from ghrah.subject.room.store import ConcurrentModificationError, RoomStore


async def _started(tmp_path: Path) -> RoomStore:
    store = RoomStore(tmp_path / "rooms.db")
    await store.start()
    return store


def _data(result: dict) -> dict:
    assert result["success"], result
    return result["data"]


async def test_room_crud_roundtrip(tmp_path: Path) -> None:
    store = await _started(tmp_path)
    try:
        record = make_room_record(project_id="proj-1", name="architecture")
        await store.upsert(record)

        loaded = await store.get(record.room_id)
        assert loaded is not None
        assert loaded.name == "architecture"
        assert loaded.project_id == "proj-1"
        assert loaded.status == "active"
        assert loaded.members == []
        assert loaded.seq_watermark == 0
        assert loaded.version == 1

        assert await store.list(project_id="proj-1") == [record]
        assert await store.list(project_id="proj-other") == []
        assert await store.list() == [record]
    finally:
        await store.stop()


async def test_update_optimistic_lock(tmp_path: Path) -> None:
    store = await _started(tmp_path)
    try:
        record = make_room_record(project_id="p", name="n")
        await store.upsert(record)

        def rename(r: RoomRecord) -> RoomRecord:
            return r.model_copy(update={"name": "renamed"})

        updated = await store.update(
            record.room_id, expected_version=None, mutator=rename
        )
        assert updated is not None
        assert updated.name == "renamed"
        assert updated.version == 2

        with pytest.raises(ConcurrentModificationError):
            await store.update(
                record.room_id, expected_version=1, mutator=rename
            )

        missing = await store.update("nope", expected_version=None, mutator=rename)
        assert missing is None
    finally:
        await store.stop()


async def test_append_log_allocates_monotonic_seq(tmp_path: Path) -> None:
    store = await _started(tmp_path)
    try:
        room = make_room_record(project_id="p", name="n")
        await store.upsert(room)

        seqs = []
        for i in range(5):
            result = await store.append_log(
                room.room_id,
                lambda seq, i=i: make_room_log_record(
                    room_id=room.room_id,
                    seq=seq,
                    author="architect",
                    author_type="agent",
                    data={"message": f"m{i}"},
                ),
            )
            assert result is not None
            record, updated_room = result
            seqs.append(record.seq)
            assert updated_room.seq_watermark == record.seq
            assert record.data == {"message": f"m{i}"}

        assert seqs == [1, 2, 3, 4, 5]

        loaded = await store.get(room.room_id)
        assert loaded is not None
        assert loaded.seq_watermark == 5

        missing = await store.append_log("nope", lambda seq: make_room_log_record(
            room_id="nope", seq=seq, author="a", author_type="agent"
        ))
        assert missing is None
    finally:
        await store.stop()


async def test_get_log_since_and_limit(tmp_path: Path) -> None:
    store = await _started(tmp_path)
    try:
        room = make_room_record(project_id="p", name="n")
        await store.upsert(room)
        for i in range(10):
            result = await store.append_log(
                room.room_id,
                lambda seq, i=i: make_room_log_record(
                    room_id=room.room_id, seq=seq, author="a",
                    author_type="agent", data={"i": i},
                ),
            )
            assert result is not None

        full = await store.get_log(room.room_id)
        assert [e.seq for e in full] == list(range(1, 11))

        since = await store.get_log(room.room_id, since_seq=7)
        assert [e.seq for e in since] == [8, 9, 10]

        tail = await store.get_log(room.room_id, limit=3)
        assert [e.seq for e in tail] == [8, 9, 10]

        empty = await store.get_log("nope")
        assert empty == []
    finally:
        await store.stop()


async def test_delete_cascades_logs_and_guards(tmp_path: Path) -> None:
    store = await _started(tmp_path)
    try:
        room = make_room_record(project_id="p", name="n")
        await store.upsert(room)
        result = await store.append_log(
            room.room_id,
            lambda seq: make_room_log_record(
                room_id=room.room_id, seq=seq, author="a", author_type="agent"
            ),
        )
        assert result is not None
        assert await store.count_logs(room.room_id) == 1

        assert await store.delete(room.room_id) is True
        assert await store.delete(room.room_id) is False
        assert await store.count_logs(room.room_id) == 0
        assert await store.get(room.room_id) is None
    finally:
        await store.stop()
