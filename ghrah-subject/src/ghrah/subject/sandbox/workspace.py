# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""兼容 re-export 层（W2 迁移）。

按计划 §三：保留旧 API 表面（AgentWorkspace / WorkspaceManager /
WorkspaceStatus / SnapshotError / SnapshotInfo）作为兼容桥，实际实现平移至
``ghrah.subject.workspace.providers.git.GitWorkspaceProvider``。

兼容桥只做映射不含逻辑（W5 store/orphan adopt 在 Manager 重建后补）：
- ``AgentWorkspace`` 包装 WorkspaceRecord + GitWorkspaceProvider，方法委托；
- ``WorkspaceManager`` 以 agent_name 为键构建 git 类型默认 workspace，内存登记
  （无持久化，与原行为一致；W4/W5 接 store）。

现有 6 个 WORKSPACE_* 命令与生产调用方（ForwardUnit / ability_runner /
Observer SDK）经此桥零改动。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ghrah.subject.workspace import (
    GitWorkspaceProvider,
    SnapshotError,
    WorkspaceProviderError,
    WorkspaceRecord,
    path_to_locator,
)
from ghrah.subject.workspace import (
    SnapshotInfo as _NewSnapshotInfo,
)

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


@dataclass
class WorkspaceStatus:
    """工作区 Git 状态（兼容旧形态）。

    由 :meth:`AgentWorkspace.status` 从 provider 通用 status 的 extra 映射而来，
    保留 branch/is_clean/staged_files/unstaged_files/untracked_files 字段以维持
    现有调用方与测试零改动。
    """

    branch: str
    is_clean: bool
    staged_files: list[str]
    unstaged_files: list[str]
    untracked_files: list[str]


# 兼容旧导入名（指向新包的 pydantic SnapshotInfo）。
SnapshotInfo = _NewSnapshotInfo


@dataclass
class AgentWorkspace:
    """单个 Agent 的工作区（兼容桥）。

    包装 :class:`WorkspaceRecord` + :class:`GitWorkspaceProvider`，方法委托至
    provider，保留 .name/.path/.sandbox 旧字段。
    """

    name: str
    path: str
    sandbox: SandboxExecutor = field(repr=False)
    record: WorkspaceRecord = field(repr=False)
    provider: GitWorkspaceProvider = field(repr=False)

    async def snapshot(self, message: str = "") -> str:
        return await self.provider.snapshot(self.record, message=message)

    async def diff(self, snapshot_id: str | None = None) -> str:
        return await self.provider.diff(self.record, snapshot_id=snapshot_id)

    async def rollback(self, snapshot_id: str) -> None:
        await self.provider.rollback(self.record, snapshot_id)

    async def status(self) -> WorkspaceStatus:
        ws_status = await self.provider.status(self.record)
        extra = ws_status.extra
        return WorkspaceStatus(
            branch=str(extra.get("branch", "main")),
            is_clean=bool(extra.get("is_clean", True)),
            staged_files=list(extra.get("staged_files", [])),
            unstaged_files=list(extra.get("unstaged_files", [])),
            untracked_files=list(extra.get("untracked_files", [])),
        )

    async def list_snapshots(self, max_count: int = 50) -> list[SnapshotInfo]:
        return await self.provider.list_snapshots(self.record, max_count=max_count)


class WorkspaceManager:
    """Agent 工作区管理器（兼容桥）。

    以 agent_name 为键构建 git 类型默认 workspace（``<root_path>/<agent_name>``），
    内存登记（无持久化，与原行为一致）。实际 git 操作经 GitWorkspaceProvider。
    """

    def __init__(
        self,
        root_path: str,
        sandbox: SandboxExecutor | None = None,
        owns_sandbox: bool = True,
    ) -> None:
        self._root_path = os.path.abspath(root_path)
        self.sandbox = sandbox
        self._owns_sandbox = owns_sandbox
        self._workspaces: dict[str, AgentWorkspace] = {}

    async def start(self) -> None:
        os.makedirs(self._root_path, exist_ok=True)
        if self.sandbox and self._owns_sandbox:
            await self.sandbox.start()

    async def stop(self) -> None:
        self._workspaces.clear()
        if self.sandbox and self._owns_sandbox:
            await self.sandbox.stop()

    @property
    def root_path(self) -> str:
        return self._root_path

    async def create_workspace(self, agent_name: str) -> AgentWorkspace:
        if agent_name in self._workspaces:
            return self._workspaces[agent_name]

        if self.sandbox is None:
            raise SnapshotError("SandboxExecutor is required for workspace operations")

        ws_path = os.path.join(self._root_path, agent_name)
        record = WorkspaceRecord(
            name=agent_name,
            provider_type="git",
            locator=path_to_locator(ws_path),
        )
        provider = GitWorkspaceProvider(self.sandbox)
        try:
            await provider.init(record)
        except WorkspaceProviderError as exc:
            # provider init 失败透传为 SnapshotError 以兼容旧错误类型契约
            raise SnapshotError(str(exc)) from exc

        workspace = AgentWorkspace(
            name=agent_name,
            path=ws_path,
            sandbox=self.sandbox,
            record=record,
            provider=provider,
        )
        self._workspaces[agent_name] = workspace
        logger.info("Created workspace for agent '%s' at %s", agent_name, ws_path)
        return workspace

    async def destroy_workspace(self, agent_name: str) -> None:
        workspace = self._workspaces.pop(agent_name, None)
        if workspace is None:
            return
        await workspace.provider.destroy(workspace.record)
        logger.info("Destroyed workspace for agent '%s' at %s", agent_name, workspace.path)

    def get_workspace(self, agent_name: str) -> AgentWorkspace | None:
        return self._workspaces.get(agent_name)

    def list_workspaces(self) -> list[str]:
        return list(self._workspaces.keys())
