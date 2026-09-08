# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WorkspaceProvider 抽象基类 + 能力位。

挂载语义下 workspace 收敛为「登记 + 授权 + 解挂」三件事，对挂载目录零
物理操作。provider 只承载两类职责：

- ``init``：create_workspace 路径的目录创建（ghrah 新建默认 workspace）；
- ``status``：存在性/可写性查询。

版本控制能力（snapshot/rollback/diff）已随 legacy GitWorkspaceProvider
整体移除：注册面对挂载目录结构性零写入，快照需求由 harness 侧
shadow-git checkpoint 库承接（backlog，见
plans/planning/2026-09-08-dogfood-prereq-fix.md §A3）。

locator 语义：FILESYSTEM_BACKED capability 为真时 locator 必为
``file://`` 且可解析出本地路径（供 sandbox cwd 裁决）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ghrah.subject.workspace.models import WorkspaceRecord, WorkspaceStatus

__all__ = [
    "WorkspaceCaps",
    "WorkspaceProvider",
]


class WorkspaceCaps(Flag):
    """Workspace provider 能力位（按位组合，capability 判定分派）。

    Attributes:
        FILESYSTEM_BACKED: 有真实文件系统根，locator 为 file://，
            可参与 sandbox cwd 限制与路径裁决。
    """

    FILESYSTEM_BACKED = auto()


class WorkspaceProvider(ABC):
    """Workspace 物理后端 provider 抽象基类。

    子类通过类变量声明身份与能力：
        - :attr:`provider_type`: provider 注册表分派键（如 "plain"）。
        - :attr:`capabilities`: capability 位组合。

    生命周期：init（仅 create_workspace 路径的目录创建）→ status（查询）。
    解挂（store 软删 + sandbox 授权解除）由 manager 承担，provider 无
    destroy 语义——挂载目录永不因 workspace 生命周期被物理删除。
    """

    provider_type: ClassVar[str]
    capabilities: ClassVar[WorkspaceCaps]

    @abstractmethod
    async def init(self, record: WorkspaceRecord) -> None:
        """按 locator 创建目录（幂等，目录已存在则直接返回）。

        仅 create_workspace（ghrah 新建默认 workspace）路径调用；
        register_workspace 登记已有目录，不触本方法。

        Raises:
            ProviderError: 创建失败（不可写等）。
        """
        raise NotImplementedError

    @abstractmethod
    async def status(self, record: WorkspaceRecord) -> WorkspaceStatus:
        """查询物理后端状态（存在性/可写性 + provider 自定义状态键）。"""
        raise NotImplementedError
