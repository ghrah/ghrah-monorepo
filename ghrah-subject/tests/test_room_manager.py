# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""RoomManager 单测：10 命令 + 写时校验 + 事件面 + send 收敛点。

契约基准 = mock-server ``state.ts``（同 payload schema / 同事件名 /
同 seq 分配语义 / 同 result 形状）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghrah.subject.room.manager import RoomManager
from ghrah.subject.room.store import RoomStore

PROJECT_IDS = {"proj-1"}


async def _manager(
    tmp_path: Path, events: list[tuple[str, dict[str, Any]]] | None = None
) -> RoomManager:
    store = RoomStore(tmp_path / "rooms.db")
    await store.start()

    async def on_event(event_type: str, payload: dict[str, Any]) -> None:
        if events is not None:
            events.append((event_type, payload))

    async def project_exists(project_id: str) -> bool:
        return project_id in PROJECT_IDS

    return RoomManager(store, on_event=on_event, project_exists=project_exists)


def _data(result: dict) -> dict:
    assert result["success"], result
    return result["data"]


async def _make_room(m: RoomManager, name: str = "architecture") -> dict:
    result = await m.handle_command(
        "room_create", {"project_id": "proj-1", "name": name}
    )
    return _data(result)["room"]


async def test_create_validates_project_and_name(tmp_path: Path) -> None:
    m = await _manager(tmp_path)
    try:
        bad_project = await m.handle_command(
            "room_create", {"project_id": "nope", "name": "n"}
        )
        assert not bad_project["success"]
        assert "project not found" in bad_project["error"]

        blank = await m.handle_command(
            "room_create", {"project_id": "proj-1", "name": "  "}
        )
        assert not blank["success"]

        missing = await m.handle_command("room_create", {"name": "n"})
        assert not missing["success"]
        assert "project_id required" in missing["error"]
    finally:
        await m.store.stop()


async def test_create_list_get_event_flow(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    m = await _manager(tmp_path, events)
    try:
        room = await _make_room(m)
        assert room["status"] == "active"
        assert room["version"] == 1
        assert events[0][0] == "room_created"
        assert events[0][1]["room"]["room_id"] == room["room_id"]

        other = await _make_room(m, "frontend")
        listed = _data(
            await m.handle_command("room_list", {"project_id": "proj-1"})
        )
        assert listed["count"] == 2
        assert {r["name"] for r in listed["rooms"]} == {"architecture", "frontend"}

        got = _data(await m.handle_command("room_get", {"room_id": room["room_id"]}))
        assert got["room"]["room_id"] == room["room_id"]

        missing = await m.handle_command("room_get", {"room_id": "nope"})
        assert not missing["success"]
        del other
    finally:
        await m.store.stop()


async def test_update_optimistic_lock_and_event(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    m = await _manager(tmp_path, events)
    try:
        room = await _make_room(m)
        updated = _data(
            await m.handle_command(
                "room_update",
                {"room_id": room["room_id"], "name": "v2", "expected_version": 1},
            )
        )["room"]
        assert updated["name"] == "v2"
        assert updated["version"] == 2
        assert events[-1][0] == "room_updated"

        conflict = await m.handle_command(
            "room_update",
            {"room_id": room["room_id"], "name": "v3", "expected_version": 1},
        )
        assert not conflict["success"]
        assert "version conflict" in conflict["error"]
    finally:
        await m.store.stop()


async def test_delete_force_guard(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    m = await _manager(tmp_path, events)
    try:
        room = await _make_room(m)
        await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "human:yuki",
                "author_type": "human",
                "data": {"message": "hi"},
            },
        )
        guarded = await m.handle_command(
            "room_delete", {"room_id": room["room_id"]}
        )
        assert not guarded["success"]
        assert "force=true" in guarded["error"]

        forced = _data(
            await m.handle_command(
                "room_delete", {"room_id": room["room_id"], "force": True}
            )
        )
        assert forced == {
            "room_id": room["room_id"],
            "project_id": "proj-1",
        }
        assert events[-1][0] == "room_deleted"
    finally:
        await m.store.stop()


async def test_join_leave_membership_and_events(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    m = await _manager(tmp_path, events)
    try:
        room = await _make_room(m)

        joined = _data(
            await m.handle_command(
                "room_join",
                {
                    "room_id": room["room_id"],
                    "subject": "architect",
                    "subject_type": "agent",
                },
            )
        )["room"]
        assert [mm["subject"] for mm in joined["members"]] == ["architect"]
        assert events[-1][0] == "room_member_joined"
        assert events[-1][1]["member"]["subject"] == "architect"

        # 幂等 join：成功但不发事件
        again = await m.handle_command(
            "room_join",
            {
                "room_id": room["room_id"],
                "subject": "architect",
                "subject_type": "agent",
            },
        )
        assert again["success"]
        assert events[-1][0] == "room_member_joined"

        members = _data(
            await m.handle_command(
                "room_get_members", {"room_id": room["room_id"]}
            )
        )
        assert members["count"] == 1
        assert members["room_id"] == room["room_id"]

        left = _data(
            await m.handle_command(
                "room_leave",
                {"room_id": room["room_id"], "subject": "architect"},
            )
        )["room"]
        assert left["members"] == []
        assert events[-1][0] == "room_member_left"
        assert events[-1][1]["subject"] == "architect"

        not_member = await m.handle_command(
            "room_leave", {"room_id": room["room_id"], "subject": "ghost"}
        )
        assert not not_member["success"]
    finally:
        await m.store.stop()


async def test_send_seq_allocation_events_and_validation(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    m = await _manager(tmp_path, events)
    try:
        room = await _make_room(m)
        await m.handle_command(
            "room_join",
            {
                "room_id": room["room_id"],
                "subject": "architect",
                "subject_type": "agent",
            },
        )

        entry = _data(
            await m.handle_command(
                "room_send",
                {
                    "room_id": room["room_id"],
                    "author": "human:yuki",
                    "author_type": "human",
                    "data": {"message": "hello", "targets": ["architect"]},
                },
            )
        )["entry"]
        assert entry["seq"] == 1
        assert entry["author_type"] == "human"
        assert events[-1][0] == "room_log_appended"
        assert events[-1][1]["entry"]["id"] == entry["id"]

        second = _data(
            await m.handle_command(
                "room_send",
                {
                    "room_id": room["room_id"],
                    "author": "architect",
                    "author_type": "agent",
                    "data": {"message": "world"},
                },
            )
        )["entry"]
        assert second["seq"] == 2

        # agent 作者必须是成员
        outsider = await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "ghost",
                "author_type": "agent",
                "data": {"message": "x"},
            },
        )
        assert not outsider["success"]
        assert "author not in room" in outsider["error"]

        # targets ⊆ room agent 成员
        bad_target = await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "human:yuki",
                "author_type": "human",
                "data": {"message": "x", "targets": ["not-member"]},
            },
        )
        assert not bad_target["success"]
        assert "target not in room" in bad_target["error"]

        bad_type = await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "human:yuki",
                "author_type": "human",
                "data": {"message": "x", "targets": "architect"},
            },
        )
        assert not bad_type["success"]
        assert "invalid targets" in bad_type["error"]
    finally:
        await m.store.stop()


async def test_get_log_since_limit(tmp_path: Path) -> None:
    m = await _manager(tmp_path)
    try:
        room = await _make_room(m)
        for i in range(5):
            await m.handle_command(
                "room_send",
                {
                    "room_id": room["room_id"],
                    "author": "human:yuki",
                    "author_type": "human",
                    "data": {"message": str(i)},
                },
            )
        result = _data(
            await m.handle_command(
                "room_get_log",
                {"room_id": room["room_id"], "since_seq": 3, "limit": 10},
            )
        )
        assert result["count"] == 2
        assert [e["seq"] for e in result["entries"]] == [4, 5]
    finally:
        await m.store.stop()


async def test_append_log_direct_convergence(tmp_path: Path) -> None:
    """send 收敛点：append_log 直调（send ability serial 等价路径）与 room_send
    命令同语义——seq 连续、事件同形。"""
    events: list[tuple[str, dict[str, Any]]] = []
    m = await _manager(tmp_path, events)
    try:
        room = await _make_room(m)
        await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "human:yuki",
                "author_type": "human",
                "data": {"message": "via command"},
            },
        )
        direct = _data(
            await m.append_log(
                room["room_id"],
                author="architect",
                author_type="agent",
                data={"message": "via ability"},
            )
        )["entry"]
        assert direct["seq"] == 2
        assert events[-1][1]["entry"]["data"]["message"] == "via ability"

        missing = await m.append_log("nope", author="a", author_type="agent")
        assert not missing["success"]
    finally:
        await m.store.stop()


async def test_resolve_recipients_union_dedup(tmp_path: Path) -> None:
    m = await _manager(tmp_path)
    try:
        r1 = await _make_room(m, "architecture")
        r2 = await _make_room(m, "frontend")
        for room, members in ((r1, ["architect", "frontend-dev"]), (r2, ["architect", "tester"])):
            for subject in members:
                result = await m.handle_command(
                    "room_join",
                    {
                        "room_id": room["room_id"],
                        "subject": subject,
                        "subject_type": "agent",
                    },
                )
                assert result["success"]

        # human 成员不计入 recipients
        await m.handle_command(
            "room_join",
            {
                "room_id": r1["room_id"],
                "subject": "human:yuki",
                "subject_type": "human",
            },
        )

        resolved = _data(
            await m.resolve_recipients(
                [r1["room_id"], r2["room_id"]], extra_targets=["architect", "extern"]
            )
        )
        assert resolved["recipients"] == ["architect", "frontend-dev", "tester", "extern"]
        assert len(resolved["rooms"]) == 2

        missing = await m.resolve_recipients(["nope"])
        assert not missing["success"]
    finally:
        await m.store.stop()


async def test_unknown_command(tmp_path: Path) -> None:
    m = await _manager(tmp_path)
    try:
        result = await m.handle_command("room_nope", {})
        assert not result["success"]
        assert "unknown command" in result["error"]
    finally:
        await m.store.stop()


# ─── human 消息投递（投递回路补全：fire-and-forget + targets 解析） ───


async def _delivery_manager(
    tmp_path: Path,
    deliveries: list[tuple[str, str, str]],
    events: list[tuple[str, dict[str, Any]]] | None = None,
) -> RoomManager:
    store = RoomStore(tmp_path / "rooms.db")
    await store.start()

    async def on_event(event_type: str, payload: dict[str, Any]) -> None:
        if events is not None:
            events.append((event_type, payload))

    async def project_exists(project_id: str) -> bool:
        return project_id in PROJECT_IDS

    async def deliver(
        target: str, sender: str, content: str, room_id: str
    ) -> dict[str, Any]:
        deliveries.append((target, sender, content))
        return {"success": True, "data": {"content": "ok"}, "error": None}

    return RoomManager(
        store, on_event=on_event, project_exists=project_exists, deliver=deliver
    )


async def _join(m: RoomManager, room_id: str, subject: str, subject_type: str) -> None:
    result = await m.handle_command(
        "room_join",
        {"room_id": room_id, "subject": subject, "subject_type": subject_type},
    )
    assert result["success"], result


async def _drain_delivery_tasks() -> None:
    import asyncio

    for task in asyncio.all_tasks():
        if task is not asyncio.current_task() and not task.done():
            await asyncio.wait([task], timeout=2.0)


async def test_human_send_delivers_to_targets(tmp_path: Path) -> None:
    """data.targets 优先：只投递 targets 内的 agent 成员，排除作者。"""
    deliveries: list[tuple[str, str, str]] = []
    m = await _delivery_manager(tmp_path, deliveries)
    try:
        room = await _make_room(m)
        await _join(m, room["room_id"], "architect", "agent")
        await _join(m, room["room_id"], "frontend-dev", "agent")

        result = await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "human:yuki",
                "author_type": "human",
                "data": {"message": "你好", "targets": ["architect"]},
            },
        )
        assert result["success"], result
        await _drain_delivery_tasks()
        assert deliveries == [("architect", "human:yuki", "你好")]
    finally:
        await m.store.stop()


async def test_human_send_broadcasts_to_all_agents_when_no_targets(tmp_path: Path) -> None:
    """缺省 targets：整室 agent 成员投递；human 成员与作者排除。"""
    deliveries: list[tuple[str, str, str]] = []
    m = await _delivery_manager(tmp_path, deliveries)
    try:
        room = await _make_room(m)
        await _join(m, room["room_id"], "architect", "agent")
        await _join(m, room["room_id"], "frontend-dev", "agent")
        await _join(m, room["room_id"], "human:yuki", "human")

        result = await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "human:yuki",
                "author_type": "human",
                "data": {"message": "hi all"},
            },
        )
        assert result["success"], result
        await _drain_delivery_tasks()
        assert sorted(deliveries) == [
            ("architect", "human:yuki", "hi all"),
            ("frontend-dev", "human:yuki", "hi all"),
        ]
    finally:
        await m.store.stop()


async def test_agent_send_not_delivered(tmp_path: Path) -> None:
    """author_type=agent 不投递（作者即发送者，回路由对端 send ability 承担）。"""
    deliveries: list[tuple[str, str, str]] = []
    m = await _delivery_manager(tmp_path, deliveries)
    try:
        room = await _make_room(m)
        await _join(m, room["room_id"], "architect", "agent")
        await _join(m, room["room_id"], "frontend-dev", "agent")

        result = await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "architect",
                "author_type": "agent",
                "data": {"message": "done", "targets": ["frontend-dev"]},
            },
        )
        assert result["success"], result
        await _drain_delivery_tasks()
        assert deliveries == []
    finally:
        await m.store.stop()


async def test_delivery_failure_does_not_affect_room_send(tmp_path: Path) -> None:
    """投递异常/被拒：fire-and-forget，不阻断回执、不重试。"""
    deliveries: list[tuple[str, str, str]] = []
    store = RoomStore(tmp_path / "rooms.db")
    await store.start()

    async def deliver(
        target: str, sender: str, content: str, room_id: str
    ) -> dict[str, Any]:
        deliveries.append((target, sender, content))
        if target == "bad":
            raise RuntimeError("boom")
        return {"success": False, "data": None, "error": "rejected"}

    m = RoomManager(store, deliver=deliver)
    try:
        room = await _make_room(m)
        await _join(m, room["room_id"], "bad", "agent")
        result = await m.handle_command(
            "room_send",
            {
                "room_id": room["room_id"],
                "author": "human:yuki",
                "author_type": "human",
                "data": {"message": "x"},
            },
        )
        assert result["success"], result
        assert result["data"]["entry"]["seq"] == 1
        await _drain_delivery_tasks()
        assert deliveries == [("bad", "human:yuki", "x")]
    finally:
        await m.store.stop()
