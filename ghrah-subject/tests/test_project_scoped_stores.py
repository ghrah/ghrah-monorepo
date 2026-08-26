from __future__ import annotations

from pathlib import Path

from ghrah.subject.project.paths import ProjectPaths
from ghrah.subject.project.scoped_stores import (
    ProjectScopedRoomStore,
    ProjectScopedTaskStore,
)
from ghrah.subject.room.models import make_room_log_record, make_room_record
from ghrah.subject.room.store import RoomStore
from ghrah.subject.task.models import make_task_record
from ghrah.subject.task.store import TaskStore
from ghrah.subject.workspace.providers.git import path_to_locator


async def test_task_records_migrate_to_project_root(tmp_path: Path) -> None:
    project_id = "project-a"
    legacy_path = tmp_path / "subject.db"
    paths = ProjectPaths.from_locator(path_to_locator(str(tmp_path / "root-a")))
    paths.initialize(project_id)
    legacy = TaskStore(legacy_path)
    await legacy.start()
    task = make_task_record(title="legacy", project_id=project_id)
    await legacy.upsert(task)
    await legacy.stop()

    async def roots() -> dict[str, str]:
        return {project_id: paths.root_locator}

    scoped = ProjectScopedTaskStore(str(legacy_path), roots)
    await scoped.start()
    try:
        assert await scoped.migrate_all() == 1
        assert (await scoped.get(task.task_id)) == task
        assert await scoped.migrate_all() == 0
    finally:
        await scoped.stop()

    old = TaskStore(legacy_path)
    target = TaskStore(paths.task_db_path)
    await old.start()
    await target.start()
    try:
        assert await old.get(task.task_id, include_deleted=True) is None
        assert await target.get(task.task_id) == task
    finally:
        await old.stop()
        await target.stop()


async def test_room_and_logs_migrate_to_project_root(tmp_path: Path) -> None:
    project_id = "project-a"
    legacy_path = tmp_path / "subject.db"
    paths = ProjectPaths.from_locator(path_to_locator(str(tmp_path / "root-a")))
    paths.initialize(project_id)
    legacy = RoomStore(legacy_path)
    await legacy.start()
    room = make_room_record(project_id=project_id, name="legacy")
    await legacy.upsert(room)
    await legacy.append_log(
        room.room_id,
        lambda seq: make_room_log_record(
            room_id=room.room_id,
            seq=seq,
            author="user",
            author_type="human",
            data={"message": "hello"},
        ),
    )
    await legacy.stop()

    async def roots() -> dict[str, str]:
        return {project_id: paths.root_locator}

    scoped = ProjectScopedRoomStore(str(legacy_path), roots)
    await scoped.start()
    try:
        assert await scoped.migrate_all() == 1
        migrated = await scoped.get(room.room_id)
        assert migrated is not None
        assert migrated.seq_watermark == 1
        logs = await scoped.get_log(room.room_id)
        assert [item.data for item in logs] == [{"message": "hello"}]
        assert await scoped.migrate_all() == 0
    finally:
        await scoped.stop()

    old = RoomStore(legacy_path)
    await old.start()
    try:
        assert await old.get(room.room_id) is None
    finally:
        await old.stop()
