# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""TaskUnit integration tests (S3a.5 routing/broadcast acceptance)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SUBJECT_CORE_EVENT_RECEIVED
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import TASK_MANAGER
from ghrah.subject.task.manager import TaskManager
from ghrah.subject.units.task import TaskUnit


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


def _data(result: dict[str, Any]) -> dict[str, Any]:
    assert result["success"], result
    return result["data"]


async def _dispatch(
    engine: SubjectEngine, command: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return await engine.dispatch_observer_command(command, payload)


async def test_task_unit_registered_and_service_available(tmp_path: Path) -> None:
    engine = SubjectEngine(_config(tmp_path))
    engine.register_builtin_units(profile="coexistence")
    await engine.start()
    try:
        unit = engine.get_unit("task")
        assert isinstance(unit, TaskUnit)
        manager = engine.context.services.require(TASK_MANAGER)
        assert isinstance(manager, TaskManager)
    finally:
        await engine.stop()


async def test_task_create_via_dispatcher_routes_to_taskunit(
    tmp_path: Path,
) -> None:
    engine = SubjectEngine(_config(tmp_path))
    engine.register_builtin_units(profile="coexistence")
    await engine.start()
    try:
        result = await _dispatch(
            engine,
            "task_create",
            {"title": "alpha task", "project_id": "proj-1", "agent_name": "alpha"},
        )
        assert result["success"]
        task = result["data"]["task"]
        assert task["title"] == "alpha task"
        assert len(task["task_id"]) == 32
        assert task["status"] == "pending"
    finally:
        await engine.stop()


async def test_task_event_broadcast_to_core_event_bus(tmp_path: Path) -> None:
    engine = SubjectEngine(_config(tmp_path))
    engine.register_builtin_units(profile="coexistence")
    emitted: list[tuple[str, dict[str, Any]]] = []

    async def collect(event_type: str, payload: Any) -> None:
        emitted.append((event_type, payload))

    engine.event_bus.subscribe(SUBJECT_CORE_EVENT_RECEIVED, collect)
    await engine.start()
    try:
        result = await _dispatch(
            engine,
            "task_create",
            {"title": "t", "project_id": "proj-1", "agent_name": "alpha"},
        )
        task = result["data"]["task"]
        core_events = [e for e in emitted if e[0] == SUBJECT_CORE_EVENT_RECEIVED]
        assert core_events, "expected a SUBJECT_CORE_EVENT_RECEIVED broadcast"
        event_type, payload = core_events[-1]
        assert event_type == SUBJECT_CORE_EVENT_RECEIVED
        assert payload["event_type"] == "task_created"
        inner = payload["payload"]
        assert inner["task"]["task_id"] == task["task_id"]
        # 顶层 agent_name hoist
        assert inner["agent_name"] == "alpha"
        # wire 形态：无 version / deleted_at
        assert "version" not in inner["task"]
        assert "deleted_at" not in inner["task"]
    finally:
        await engine.stop()


async def test_end_to_end_lifecycle_protected_delete(tmp_path: Path) -> None:
    engine = SubjectEngine(_config(tmp_path))
    engine.register_builtin_units(profile="coexistence")
    await engine.start()
    try:
        b = _data(
            await _dispatch(
                engine,
                "task_create",
                {"title": "b", "project_id": "proj-1", "agent_name": "a"},
            )
        )["task"]
        a = _data(
            await _dispatch(
                engine,
                "task_create",
                {
                    "title": "a",
                    "project_id": "proj-1",
                    "dependencies": [b["task_id"]],
                    "agent_name": "a",
                },
            )
        )["task"]

        # start a 被拒：依赖未完成
        blocked = await _dispatch(engine, "task_start", {"task_id": a["task_id"]})
        assert not blocked["success"]
        assert "dependencies not completed" in blocked["error"]

        # 完成 b 后 start a 成功
        await _dispatch(engine, "task_complete", {"task_id": b["task_id"]})
        started = _data(await _dispatch(engine, "task_start", {"task_id": a["task_id"]}))
        assert started["task"]["status"] == "in_progress"
        assert started["task"]["started_at"] is not None

        # 完成 a
        await _dispatch(engine, "task_complete", {"task_id": a["task_id"]})

        # 保护删除 b：仍有 dependents（a 未软删）被拒
        protected = await _dispatch(engine, "task_delete", {"task_id": b["task_id"]})
        assert not protected["success"]
        assert "dependents" in protected["error"]

        # force 软删 b 成功
        deleted = _data(
            await _dispatch(
                engine, "task_delete", {"task_id": b["task_id"], "force": True}
            )
        )
        assert deleted["task_id"] == b["task_id"]

        # 删后 get / list 不返回 b
        miss = await _dispatch(engine, "task_get", {"task_id": b["task_id"]})
        assert not miss["success"]
        listing = _data(
            await _dispatch(
                engine, "task_list", {"include_terminal": True, "limit": 100}
            )
        )
        ids = {t["task_id"] for t in listing["tasks"]}
        assert b["task_id"] not in ids
    finally:
        await engine.stop()
