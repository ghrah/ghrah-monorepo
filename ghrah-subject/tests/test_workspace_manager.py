# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""W5 WorkspaceManager 重构验收：workspace_id 键控 + store 恢复 + orphan adopt
+ agent_name 兼容桥 + 未 start 退化路径。

不依赖现有 test_sandbox.py 的兼容用例（那些保留为零回归基线），此处新增 W5
契约用例：
- 重启后 registry 从 store 恢复；
- orphan adopt：有 marker 未注册目录经 start 扫描补登；
- 未 start 也能用：create_workspace 在 store 未就绪时仅 init + 内存登记，
  随后 start 时 orphan adopt 补登 store；
- subject_id 不匹配的 orphan 目录不误认领；
- workspace_id 一等查询接口。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.sandbox.workspace import WorkspaceManager
from ghrah.subject.workspace import WorkspaceRecord, path_to_locator

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


class _Sandbox:
    def __init__(self, root: str) -> None:
        self.executor = SandboxExecutor(workspace_root=root)

    async def __aenter__(self) -> SandboxExecutor:
        await self.executor.start()
        return self.executor

    async def __aexit__(self, *exc: object) -> None:
        await self.executor.stop()


def _sandbox_root(tmp_path: Path) -> str:
    return str(tmp_path / "root")


def _db(tmp_path: Path) -> str:
    return str(tmp_path / "workspaces.db")


# ─── 1. 重启后 registry 从 store 恢复 ───


class TestRestartRestoreFromStore:
    async def test_restart_reloads_workspaces(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        async with _Sandbox(root) as sandbox:
            manager = WorkspaceManager(root_path=root, sandbox=sandbox, db_path=db)
            await manager.start()
            ws = await manager.create_workspace("agent-a")
            assert manager.get_workspace("agent-a") is ws
            await manager.stop()

        async with _Sandbox(root) as sandbox2:
            manager2 = WorkspaceManager(root_path=root, sandbox=sandbox2, db_path=db)
            await manager2.start()
            # 从 store 恢复：agent-a 仍在索引中
            assert manager2.get_workspace("agent-a") is not None
            assert manager2.list_workspaces() == ["agent-a"]
            # workspace_id 一等查询
            wid = manager2.get_workspace("agent-a").record.workspace_id  # type: ignore[union-attr]
            assert manager2.get_workspace_by_id(wid) is not None
            await manager2.stop()

    async def test_destroy_persists_soft_delete(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        async with _Sandbox(root) as sandbox:
            manager = WorkspaceManager(root_path=root, sandbox=sandbox, db_path=db)
            await manager.start()
            await manager.create_workspace("agent-x")
            await manager.destroy_workspace("agent-x")
            await manager.stop()

        async with _Sandbox(root) as sandbox2:
            manager2 = WorkspaceManager(root_path=root, sandbox=sandbox2, db_path=db)
            await manager2.start()
            assert manager2.get_workspace("agent-x") is None
            assert manager2.list_workspaces() == []
            await manager2.stop()


# ─── 2. orphan adopt 扫描 ───


class TestOrphanAdopt:
    async def test_orphan_with_marker_adopted_on_start(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        async with _Sandbox(root) as sandbox:
            # 先在 root 下 init 一个 git workspace（marker 落盘），但不登记 store
            from ghrah.subject.workspace import GitWorkspaceProvider

            ws_path = os.path.join(root, "orphan-agent")
            record = WorkspaceRecord(
                name="orphan-agent",
                provider_type="git",
                subject_id="default",
                locator=path_to_locator(ws_path),
            )
            provider = GitWorkspaceProvider(sandbox)
            await provider.init(record)

            manager = WorkspaceManager(root_path=root, sandbox=sandbox, db_path=db)
            await manager.start()
            # orphan adopt 应认领该目录
            assert manager.get_workspace("orphan-agent") is not None
            assert manager.get_workspace("orphan-agent").record.workspace_id == record.workspace_id  # type: ignore[union-attr]
            await manager.stop()

    async def test_orphan_subject_id_mismatch_not_adopted(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        async with _Sandbox(root) as sandbox:
            from ghrah.subject.workspace import GitWorkspaceProvider

            ws_path = os.path.join(root, "other-subject-agent")
            record = WorkspaceRecord(
                name="other-subject-agent",
                provider_type="git",
                subject_id="other",  # 不同 subject
                locator=path_to_locator(ws_path),
            )
            provider = GitWorkspaceProvider(sandbox)
            await provider.init(record)

            manager = WorkspaceManager(
                root_path=root, sandbox=sandbox, db_path=db, subject_id="default"
            )
            await manager.start()
            # subject_id 不匹配 → 不认领
            assert manager.get_workspace("other-subject-agent") is None
            await manager.stop()

    async def test_no_marker_dir_not_adopted(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        os.makedirs(os.path.join(root, "plain-dir"))  # 无 marker
        async with _Sandbox(root) as sandbox:
            manager = WorkspaceManager(root_path=root, sandbox=sandbox, db_path=db)
            await manager.start()
            assert manager.get_workspace("plain-dir") is None
            await manager.stop()


# ─── 3. 未 start 退化路径（store 未就绪也能用）───


class TestStoreNotStartedDegradation:
    async def test_create_workspace_without_start(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        async with _Sandbox(root) as sandbox:
            manager = WorkspaceManager(root_path=root, sandbox=sandbox, db_path=db)
            # 未 start() 直接 create：降级为仅 init + 内存登记
            ws = await manager.create_workspace("agent-no-start")
            assert os.path.isdir(ws.path)
            assert os.path.isfile(os.path.join(ws.path, ".ghrah-workspace"))
            assert manager.get_workspace("agent-no-start") is ws
            # store 未就绪 → 未登记
            assert manager.get_record(ws.record.workspace_id) is not None  # 内存有
            # 后续 start() orphan adopt 应补登 store（marker 已落盘，同 workspace_id）
            await manager.start()
            assert manager.get_workspace("agent-no-start") is not None
            await manager.stop()

    async def test_create_then_start_persists_via_orphan_adopt(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        async with _Sandbox(root) as sandbox:
            manager = WorkspaceManager(root_path=root, sandbox=sandbox, db_path=db)
            ws = await manager.create_workspace("agent-late")
            wid = ws.record.workspace_id
            await manager.start()  # store 启动 + orphan adopt 补登
            await manager.stop()

        async with _Sandbox(root) as sandbox2:
            manager2 = WorkspaceManager(root_path=root, sandbox=sandbox2, db_path=db)
            await manager2.start()
            # 经 orphan adopt 补登后，store 应有该记录 → 重启仍恢复
            restored = manager2.get_workspace_by_id(wid)
            assert restored is not None
            await manager2.stop()


# ─── 4. 无 db_path 纯内存模式（test_sandbox.py 直接构造兼容）───


class TestInMemoryMode:
    async def test_no_db_path_works_in_memory(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        async with _Sandbox(root) as sandbox:
            manager = WorkspaceManager(root_path=root, sandbox=sandbox)
            await manager.start()
            ws = await manager.create_workspace("agent-mem")
            assert manager.get_workspace("agent-mem") is ws
            assert "agent-mem" in manager.list_workspaces()
            await manager.destroy_workspace("agent-mem")
            assert manager.get_workspace("agent-mem") is None
            await manager.stop()


# ─── 5. workspace_id 一等查询 ───


class TestWorkspaceIdFirstClass:
    async def test_get_by_id_and_list_records(self, tmp_path: Path) -> None:
        root = _sandbox_root(tmp_path)
        db = _db(tmp_path)
        async with _Sandbox(root) as sandbox:
            manager = WorkspaceManager(root_path=root, sandbox=sandbox, db_path=db)
            await manager.start()
            ws1 = await manager.create_workspace("a1")
            ws2 = await manager.create_workspace("a2")
            assert manager.get_workspace_by_id(ws1.record.workspace_id) is ws1
            ids = {r.workspace_id for r in manager.list_records()}
            assert {ws1.record.workspace_id, ws2.record.workspace_id} <= ids
            await manager.stop()
