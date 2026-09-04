# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActionSession/ActionBranch checkpoint 持久化后端接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ghrah.context.persistence.changes import ContextChanges
from ghrah.context.persistence.checkpoint import ContextCheckpoint

__all__ = ["PersistenceBackend"]


class PersistenceBackend(ABC):
    """按 Agent 保存多 Session 拓扑的异步持久化接口。"""

    @abstractmethod
    async def apply_changes(self, changes: ContextChanges) -> None:
        """在一个原子操作中应用最小增量变更集。"""

    @abstractmethod
    async def load_checkpoint(self, agent_name: str) -> ContextCheckpoint | None:
        """加载 Agent 的完整多 Session checkpoint。"""

    @abstractmethod
    async def delete_checkpoint(self, agent_name: str) -> None:
        """删除指定 Agent 的完整 checkpoint。"""

    @abstractmethod
    async def list_agents(self) -> list[str]:
        """列出所有存在 checkpoint 的 Agent 名称。"""
