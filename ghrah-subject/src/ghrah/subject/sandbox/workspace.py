from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ghrah.subject.sandbox.executor import SandboxExecutor

__all__ = [
    "WorkspaceManager",
    "AgentWorkspace",
    "WorkspaceStatus",
    "SnapshotInfo",
    "SnapshotError",
]

logger = logging.getLogger(__name__)


class SnapshotError(Exception):
    """快照操作错误。"""


@dataclass
class WorkspaceStatus:
    """工作区 Git 状态。"""

    branch: str
    is_clean: bool
    staged_files: list[str]
    unstaged_files: list[str]
    untracked_files: list[str]


@dataclass
class SnapshotInfo:
    """快照信息。"""

    commit_hash: str
    message: str
    timestamp: float


@dataclass
class AgentWorkspace:
    """单个 Agent 的工作区。

    每个工作区是一个 Git 仓库，位于 WorkspaceManager.root_path/<agent_name>/。
    """

    name: str
    path: str
    sandbox: SandboxExecutor = field(repr=False)

    async def snapshot(self, message: str = "") -> str:
        """创建快照（git add -A + git commit）。

        Returns:
            commit hash
        """
        if not message:
            import time
            message = f"snapshot at {time.time()}"

        add_result = await self.sandbox.execute_command(
            ["git", "add", "-A"], cwd=self.path,
        )
        if not add_result.success:
            raise SnapshotError(f"git add failed: {add_result.stderr}")

        status = await self.status()
        if status.is_clean:
            rev_result = await self.sandbox.execute_command(
                ["git", "rev-parse", "HEAD"], cwd=self.path,
            )
            if rev_result.success:
                return rev_result.stdout.strip()
            raise SnapshotError(f"git rev-parse HEAD failed: {rev_result.stderr}")

        commit_result = await self.sandbox.execute_command(
            ["git", "commit", "-m", message], cwd=self.path,
        )
        if not commit_result.success:
            raise SnapshotError(f"git commit failed: {commit_result.stderr}")

        rev_result = await self.sandbox.execute_command(
            ["git", "rev-parse", "HEAD"], cwd=self.path,
        )
        if not rev_result.success:
            raise SnapshotError(f"git rev-parse HEAD failed: {rev_result.stderr}")

        logger.info("Workspace '%s' snapshot: %s", self.name, rev_result.stdout.strip())
        return rev_result.stdout.strip()

    async def diff(self, snapshot_id: str | None = None) -> str:
        """获取 diff（与指定快照或工作区对比）。"""
        args = ["git", "diff"]
        if snapshot_id:
            args.append(snapshot_id)
        result = await self.sandbox.execute_command(args, cwd=self.path)
        return result.stdout

    async def rollback(self, snapshot_id: str) -> None:
        """回滚到指定快照（git checkout + git clean）。"""
        checkout_result = await self.sandbox.execute_command(
            ["git", "checkout", snapshot_id, "--", "."], cwd=self.path,
        )
        if not checkout_result.success:
            raise SnapshotError(f"git checkout failed: {checkout_result.stderr}")

        clean_result = await self.sandbox.execute_command(
            ["git", "clean", "-fd"], cwd=self.path,
        )
        if not clean_result.success and clean_result.stderr:
            logger.warning("git clean warning: %s", clean_result.stderr)

        logger.info("Workspace '%s' rolled back to %s", self.name, snapshot_id)

    async def status(self) -> WorkspaceStatus:
        """获取工作区 Git 状态。"""
        branch_result = await self.sandbox.execute_command(
            ["git", "branch", "--show-current"], cwd=self.path,
        )
        branch = branch_result.stdout.strip() or "main"

        status_result = await self.sandbox.execute_command(
            ["git", "status", "--porcelain"], cwd=self.path,
        )

        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []

        for line in status_result.stdout.splitlines():
            if not line:
                continue
            if len(line) < 4:
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

        return WorkspaceStatus(
            branch=branch,
            is_clean=not (staged or unstaged or untracked),
            staged_files=staged,
            unstaged_files=unstaged,
            untracked_files=untracked,
        )

    async def list_snapshots(self, max_count: int = 50) -> list[SnapshotInfo]:
        """列出快照历史。"""
        result = await self.sandbox.execute_command(
            ["git", "log", "--format=%H|%s|%ct", f"-n{max_count}"],
            cwd=self.path,
        )
        if not result.success:
            return []

        snapshots: list[SnapshotInfo] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                try:
                    snapshots.append(SnapshotInfo(
                        commit_hash=parts[0],
                        message=parts[1],
                        timestamp=float(parts[2]),
                    ))
                except ValueError:
                    continue
        return snapshots


class WorkspaceManager:
    """Agent 工作区管理器。

    使用 Git 作为物理文件的唯一真相源。
    利用 git diff/apply/checkout 实现状态快照与回滚。
    所有 Git 操作通过 SandboxExecutor 执行，绝对禁止阻塞主线程。
    """

    def __init__(
        self,
        root_path: str,
        sandbox: SandboxExecutor | None = None,
    ) -> None:
        self._root_path = os.path.abspath(root_path)
        self.sandbox = sandbox
        self._workspaces: dict[str, AgentWorkspace] = {}

    async def start(self) -> None:
        """初始化 WorkspaceManager。"""
        os.makedirs(self._root_path, exist_ok=True)
        if self.sandbox:
            await self.sandbox.start()

    async def stop(self) -> None:
        """清理。"""
        self._workspaces.clear()
        if self.sandbox:
            await self.sandbox.stop()

    @property
    def root_path(self) -> str:
        return self._root_path

    async def create_workspace(self, agent_name: str) -> AgentWorkspace:
        """为 Agent 创建工作区目录并初始化 Git 仓库。"""
        if agent_name in self._workspaces:
            return self._workspaces[agent_name]

        if self.sandbox is None:
            raise SnapshotError("SandboxExecutor is required for workspace operations")

        ws_path = os.path.join(self._root_path, agent_name)
        os.makedirs(ws_path, exist_ok=True)

        init_result = await self.sandbox.execute_command(
            ["git", "init"], cwd=ws_path,
        )
        if not init_result.success:
            raise SnapshotError(f"Failed to git init: {init_result.stderr}")

        await self.sandbox.execute_command(
            ["git", "config", "user.email", "agent@ghrah.local"], cwd=ws_path,
        )
        await self.sandbox.execute_command(
            ["git", "config", "user.name", f"agent-{agent_name}"], cwd=ws_path,
        )
        await self.sandbox.execute_command(
            ["git", "config", "commit.gpgsign", "false"], cwd=ws_path,
        )
        await self.sandbox.execute_command(
            ["git", "config", "tag.gpgsign", "false"], cwd=ws_path,
        )

        marker_path = os.path.join(ws_path, ".ghrah-workspace")
        with open(marker_path, "w") as f:
            f.write(f"# Workspace for agent: {agent_name}\n")

        await self.sandbox.execute_command(["git", "add", "-A"], cwd=ws_path)
        commit_result = await self.sandbox.execute_command(
            ["git", "commit", "-m", f"Initial workspace for {agent_name}"],
            cwd=ws_path,
        )
        if not commit_result.success:
            logger.warning("Initial commit failed (may be empty): %s", commit_result.stderr)

        workspace = AgentWorkspace(
            name=agent_name, path=ws_path, sandbox=self.sandbox,
        )
        self._workspaces[agent_name] = workspace
        logger.info("Created workspace for agent '%s' at %s", agent_name, ws_path)
        return workspace

    async def destroy_workspace(self, agent_name: str) -> None:
        """销毁 Agent 工作区（递归删除目录）。"""
        workspace = self._workspaces.pop(agent_name, None)
        if workspace is None:
            return

        ws_path = workspace.path
        if os.path.exists(ws_path):
            await asyncio.to_thread(shutil.rmtree, ws_path)
        logger.info("Destroyed workspace for agent '%s' at %s", agent_name, ws_path)

    def get_workspace(self, agent_name: str) -> AgentWorkspace | None:
        """获取 Agent 工作区实例。"""
        return self._workspaces.get(agent_name)

    def list_workspaces(self) -> list[str]:
        """列出所有已注册的工作区 Agent 名称。"""
        return list(self._workspaces.keys())
