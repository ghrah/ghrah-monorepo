# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""GitWorkspaceProvider：迁移自 AgentWorkspace 的 git 后端。

按计划 §2.4：provider_type="git"，capabilities = FILESYSTEM_BACKED | SNAPSHOT |
ROLLBACK | DIFF，实现 VersionedWorkspaceProvider。现有 AgentWorkspace 的全部 git
逻辑（git init/config/add/commit、snapshot=commit、diff、rollback=checkout、status、
list_snapshots）平移为 provider 方法，仍经 SandboxExecutor 执行 git 命令。

locator 语义：file:///abs/path（FILESYSTEM_BACKED），本地路径用于 sandbox cwd。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlparse

from ghrah.subject.workspace.errors import SnapshotError, WorkspaceProviderError
from ghrah.subject.workspace.marker import (
    MarkerData,
    marker_path,
    read_marker,
    write_marker,
)
from ghrah.subject.workspace.models import AdoptResult, SnapshotInfo, WorkspaceStatus
from ghrah.subject.workspace.providers.base import (
    VersionedWorkspaceProvider,
    WorkspaceCaps,
)

if TYPE_CHECKING:
    from ghrah.subject.sandbox.executor import SandboxExecutor
    from ghrah.subject.workspace.models import WorkspaceRecord

logger = logging.getLogger(__name__)

__all__ = ["GitWorkspaceProvider", "locator_to_path", "path_to_locator"]


def path_to_locator(path: str) -> str:
    """本地绝对路径 → file:// URI。"""
    return "file://" + path


def locator_to_path(locator: str) -> str:
    """file:// URI → 本地绝对路径。

    非 file:// locator（未来 nfs://、table://）抛 ValueError。
    """
    parsed = urlparse(locator)
    if parsed.scheme != "file":
        raise ValueError(f"GitWorkspaceProvider requires file:// locator, got: {locator}")
    # urlparse 对 file:///abs/path 给出 path=/abs/path；空 netloc 时直接取 path
    return parsed.path or ""


class GitWorkspaceProvider(VersionedWorkspaceProvider):
    """git 后端 provider（VersionedWorkspaceProvider）。

    所有 git 操作经注入的 SandboxExecutor 执行（不阻塞主线程）。
    """

    provider_type: ClassVar[str] = "git"
    capabilities: ClassVar[WorkspaceCaps] = (
        WorkspaceCaps.FILESYSTEM_BACKED
        | WorkspaceCaps.SNAPSHOT
        | WorkspaceCaps.ROLLBACK
        | WorkspaceCaps.DIFF
    )

    def __init__(self, sandbox: SandboxExecutor) -> None:
        self._sandbox = sandbox

    # ─── WorkspaceProvider ───

    async def init(self, record: WorkspaceRecord) -> None:
        """mkdir + git init + config + 写结构化 marker + initial commit。

        幂等：目录已存在且 marker 匹配三要素则认领式返回，不破坏现有 git 历史。
        """
        if self._sandbox is None:  # pragma: no cover - 注入契约保证非空
            raise SnapshotError("SandboxExecutor is required for git workspace init")
        ws_path = locator_to_path(record.locator)
        existing_marker = read_marker(ws_path)
        if existing_marker is not None and (
            existing_marker.workspace_id == record.workspace_id
            and existing_marker.provider_type == record.provider_type
            and existing_marker.subject_id == record.subject_id
        ):
            # 已认领式初始化：保留现有内容
            logger.debug("Git workspace %s already initialized (marker match)", record.locator)
            return

        os.makedirs(ws_path, exist_ok=True)

        init_result = await self._sandbox.execute_command(["git", "init"], cwd=ws_path)
        if not init_result.success:
            raise WorkspaceProviderError(f"Failed to git init: {init_result.stderr}")

        await self._sandbox.execute_command(
            ["git", "config", "user.email", "agent@ghrah.local"], cwd=ws_path
        )
        await self._sandbox.execute_command(
            ["git", "config", "user.name", f"agent-{record.name}"], cwd=ws_path
        )
        await self._sandbox.execute_command(
            ["git", "config", "commit.gpgsign", "false"], cwd=ws_path
        )
        await self._sandbox.execute_command(
            ["git", "config", "tag.gpgsign", "false"], cwd=ws_path
        )

        write_marker(ws_path, record)

        await self._sandbox.execute_command(["git", "add", "-A"], cwd=ws_path)
        commit_result = await self._sandbox.execute_command(
            ["git", "commit", "-m", f"Initial workspace for {record.name}"], cwd=ws_path
        )
        if not commit_result.success:
            logger.warning(
                "Initial commit failed (may be empty): %s", commit_result.stderr
            )
        logger.info("Initialized git workspace %s (%s)", record.workspace_id, ws_path)

    async def adopt(self, locator: str) -> AdoptResult | None:
        """读 marker 校验 provider_type 一致；无 marker / 旧格式 /
        marker 声明非 git 类型 → 返回 None（不误认领）。

        workspace_id / subject_id 与目标 subject 的比对由 manager 在认领时
        经 adopt_marker_matches 完成（provider 只保证 provider_type 自洽）。
        """
        ws_path = locator_to_path(locator)
        marker = read_marker(ws_path)
        if marker is None or marker.provider_type != self.provider_type:
            return None
        return _adopt_result_from_marker(marker)

    async def status(self, record: WorkspaceRecord) -> WorkspaceStatus:
        """查询 git 状态：存在性/可写性 + branch/is_clean/脏文件计数（extra）。"""
        ws_path = locator_to_path(record.locator)
        exists = os.path.isdir(ws_path) and os.path.isdir(os.path.join(ws_path, ".git"))
        writable = os.access(ws_path, os.W_OK) if exists else False

        extra: dict[str, object] = {}
        if exists:
            branch_result = await self._sandbox.execute_command(
                ["git", "branch", "--show-current"], cwd=ws_path
            )
            branch = branch_result.stdout.strip() or "main"
            status_result = await self._sandbox.execute_command(
                ["git", "status", "--porcelain"], cwd=ws_path
            )
            staged, unstaged, untracked = _parse_porcelain(status_result.stdout)
            extra = {
                "branch": branch,
                "is_clean": not (staged or unstaged or untracked),
                "staged_files": staged,
                "unstaged_files": unstaged,
                "untracked_files": untracked,
                "dirty_count": len(staged) + len(unstaged) + len(untracked),
            }
        return WorkspaceStatus(exists=exists, writable=writable, extra=extra)

    async def destroy(self, record: WorkspaceRecord) -> None:
        """递归删除目录（同现有 AgentWorkspace 语义）。"""
        ws_path = locator_to_path(record.locator)
        if os.path.exists(ws_path):
            await asyncio.to_thread(shutil.rmtree, ws_path)
        logger.info("Destroyed git workspace %s at %s", record.workspace_id, ws_path)

    # ─── VersionedWorkspaceProvider ───

    async def snapshot(self, record: WorkspaceRecord, message: str = "") -> str:
        """git add -A + git commit；无变更返回当前 HEAD。"""
        ws_path = locator_to_path(record.locator)
        if not message:
            import time

            message = f"snapshot at {time.time()}"

        add_result = await self._sandbox.execute_command(["git", "add", "-A"], cwd=ws_path)
        if not add_result.success:
            raise SnapshotError(f"git add failed: {add_result.stderr}")

        status = await self.status(record)
        is_clean = bool(status.extra.get("is_clean", True))
        if is_clean:
            rev_result = await self._sandbox.execute_command(
                ["git", "rev-parse", "HEAD"], cwd=ws_path
            )
            if rev_result.success:
                return rev_result.stdout.strip()
            raise SnapshotError(f"git rev-parse HEAD failed: {rev_result.stderr}")

        commit_result = await self._sandbox.execute_command(
            ["git", "commit", "-m", message], cwd=ws_path
        )
        if not commit_result.success:
            raise SnapshotError(f"git commit failed: {commit_result.stderr}")

        rev_result = await self._sandbox.execute_command(
            ["git", "rev-parse", "HEAD"], cwd=ws_path
        )
        if not rev_result.success:
            raise SnapshotError(f"git rev-parse HEAD failed: {rev_result.stderr}")
        logger.info(
            "Git workspace %s snapshot: %s", record.workspace_id, rev_result.stdout.strip()
        )
        return rev_result.stdout.strip()

    async def diff(self, record: WorkspaceRecord, snapshot_id: str | None = None) -> str:
        """git diff（与指定快照或工作区对比）。"""
        ws_path = locator_to_path(record.locator)
        args = ["git", "diff"]
        if snapshot_id:
            args.append(snapshot_id)
        result = await self._sandbox.execute_command(args, cwd=ws_path)
        return result.stdout

    async def rollback(self, record: WorkspaceRecord, snapshot_id: str) -> None:
        """git checkout snapshot -- . + git clean -fd。"""
        ws_path = locator_to_path(record.locator)
        checkout_result = await self._sandbox.execute_command(
            ["git", "checkout", snapshot_id, "--", "."], cwd=ws_path
        )
        if not checkout_result.success:
            raise SnapshotError(f"git checkout failed: {checkout_result.stderr}")

        clean_result = await self._sandbox.execute_command(
            ["git", "clean", "-fd"], cwd=ws_path
        )
        if not clean_result.success and clean_result.stderr:
            logger.warning("git clean warning: %s", clean_result.stderr)
        logger.info("Git workspace %s rolled back to %s", record.workspace_id, snapshot_id)

    async def list_snapshots(
        self, record: WorkspaceRecord, max_count: int = 50
    ) -> list[SnapshotInfo]:
        """git log --format 列出快照。"""
        ws_path = locator_to_path(record.locator)
        result = await self._sandbox.execute_command(
            ["git", "log", "--format=%H|%s|%ct", f"-n{max_count}"], cwd=ws_path
        )
        if not result.success:
            return []
        snapshots: list[SnapshotInfo] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                try:
                    snapshots.append(
                        SnapshotInfo(
                            commit_hash=parts[0],
                            message=parts[1],
                            timestamp=float(parts[2]),
                        )
                    )
                except ValueError:
                    continue
        return snapshots

    @staticmethod
    def has_marker(dir_path: str) -> bool:
        """目录是否存在结构化 marker（用于 orphan adopt 探测）。"""
        return os.path.isfile(marker_path(dir_path))


def _adopt_result_from_marker(marker: MarkerData) -> AdoptResult:
    return AdoptResult(
        workspace_id=marker.workspace_id,
        provider_type=marker.provider_type,
        subject_id=marker.subject_id,
        name=marker.name or "",
        created_at=marker.created_at,
    )


def _parse_porcelain(
    stdout: str,
) -> tuple[list[str], list[str], list[str]]:
    """解析 git status --porcelain 输出为 staged/unstaged/untracked。"""
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    for line in stdout.splitlines():
        if not line or len(line) < 4:
            continue
        index_char = line[0]
        work_char = line[1]
        filepath = line[3:]
        if index_char in ("M", "A", "D", "R"):
            staged.append(filepath)
        elif work_char in ("M", "D"):
            unstaged.append(filepath)
        elif index_char == "?":
            untracked.append(filepath)
    return staged, unstaged, untracked
