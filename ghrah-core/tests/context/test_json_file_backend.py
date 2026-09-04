# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""追加式 JSON v2 checkpoint 后端测试。"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from ghrah.chat.message import ChatMessage
from ghrah.context import ContextManager
from ghrah.context.persistence import JsonFileBackend


def _manager(backend: JsonFileBackend, *, agent_name: str = "agent") -> ContextManager:
    return ContextManager(agent_name=agent_name, initial_state={"step": 0}, persistence=backend)


def test_init_and_run_id(tmp_path: Path) -> None:
    """后端保留显式路径和 run 隔离标识。"""
    backend = JsonFileBackend(root_dir=tmp_path, run_id="run-a")

    assert backend.root_dir == tmp_path
    assert backend.run_id == "run-a"
    assert backend.run_dir == tmp_path / "run-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("compress", [True, False])
async def test_roundtrip_multiple_sessions_and_branches(tmp_path: Path, compress: bool) -> None:
    """压缩与非压缩记录都能恢复多 Root、多 Branch 和上下文。"""
    backend = JsonFileBackend(root_dir=tmp_path, run_id="run", compress=compress)
    manager = _manager(backend)
    manager.begin_iteration()
    manager.add_messages([ChatMessage.user(text_or_blocks="first")])
    manager.apply_state_changes({"step": 1})
    manager.commit_iteration(ability_names=["work"])
    second = manager.create_session(initial_state={"step": 20})
    manager.activate_session(second.session_id)
    retry = manager.create_branch(session_id=second.session_id, name="retry")
    manager.activate_branch(second.session_id, retry.branch_id)
    await manager.persist()

    restored = _manager(backend)
    await restored.restore("agent")

    assert len(restored.list_sessions()) == 2
    assert restored.active_session_id == second.session_id
    assert restored.get_active_session().active_branch_id == retry.branch_id
    assert restored.get_current_state() == {"step": 20}


@pytest.mark.asyncio
async def test_auto_persist_appends_constant_size_records(tmp_path: Path) -> None:
    """连续 commit 追加小记录，不覆盖包含全部历史的单一文件。"""
    backend = JsonFileBackend(root_dir=tmp_path, run_id="run", compress=False)
    manager = ContextManager(agent_name="agent", persistence=backend, auto_persist=True)
    await manager.wait_for_persist()

    for index in range(20):
        manager.begin_iteration()
        manager.commit_iteration(ability_names=[f"step-{index}"])
    await manager.wait_for_persist()

    records = sorted(backend._changes_dir("agent").glob("*.json"))
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in records]
    assert len(records) == 21
    assert [len(payload["nodes"]) for payload in payloads] == [1] * 21
    assert max(path.stat().st_size for path in records[1:]) < 4_096


@pytest.mark.asyncio
async def test_compressed_records_are_valid_gzip(tmp_path: Path) -> None:
    """压缩模式中的每条增量记录都是独立 gzip 文件。"""
    backend = JsonFileBackend(root_dir=tmp_path, run_id="run", compress=True)
    manager = _manager(backend)
    await manager.persist()

    record = next(backend._changes_dir("agent").glob("*.json.gz"))
    with gzip.open(record, "rt", encoding="utf-8") as stream:
        assert json.load(stream)["schema_version"] == 2


@pytest.mark.asyncio
async def test_list_delete_and_run_isolation(tmp_path: Path) -> None:
    """Agent 列表、删除与 run 隔离只操作自身命名空间。"""
    first = JsonFileBackend(root_dir=tmp_path, run_id="one")
    second = JsonFileBackend(root_dir=tmp_path, run_id="two")
    await _manager(first, agent_name="bravo").persist()
    await _manager(first, agent_name="alpha").persist()
    await _manager(second, agent_name="alpha").persist()

    assert await first.list_agents() == ["alpha", "bravo"]
    await first.delete_checkpoint("alpha")
    assert await first.list_agents() == ["bravo"]
    assert await second.list_agents() == ["alpha"]


@pytest.mark.asyncio
async def test_legacy_layout_fails_fast(tmp_path: Path) -> None:
    """旧 JSON 布局不会被猜测迁移。"""
    backend = JsonFileBackend(root_dir=tmp_path, run_id="run")
    agent_dir = backend._agent_dir("agent")
    agent_dir.mkdir(parents=True)
    (agent_dir / "nodes.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Legacy context checkpoint"):
        await backend.load_checkpoint("agent")
