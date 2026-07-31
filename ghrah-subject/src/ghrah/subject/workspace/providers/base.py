# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WorkspaceProvider 抽象基类 + 能力位 + 窄化版本接口。

跨 git / plain / 其他 VCS / NFS / 数据表的公共分母只有
身份、定位、初始化、认领、状态、销毁。版本控制能力（snapshot/rollback/diff）
是 git 特有能力，**不进基类签名**，经 :class:`WorkspaceCaps` capability 位 +
:class:`VersionedWorkspaceProvider` 窄化接口暴露。

调用方（命令 handler）按 ``isinstance(provider, VersionedWorkspaceProvider)``
或 capability 位判定分派；不支持时返回 CAPABILITY_NOT_SUPPORTED error，
而非 AttributeError。

locator 语义：基类不假设文件系统。FILESYSTEM_BACKED capability 为真时 locator
必为 ``file://`` 且可解析出本地路径（供 sandbox cwd / Foxtrail 裁决）；非文件系统
后端的 grant subpath 语义由 provider 自定义（MVP 不实现但模型不堵死）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ghrah.subject.workspace.models import (
        AdoptResult,
        SnapshotInfo,
        WorkspaceRecord,
        WorkspaceStatus,
    )

__all__ = [
    "WorkspaceCaps",
    "WorkspaceProvider",
    "VersionedWorkspaceProvider",
]


class WorkspaceCaps(Flag):
    """Workspace provider 能力位（按位组合，capability 判定分派）。

    Attributes:
        FILESYSTEM_BACKED: 有真实文件系统根，locator 为 file://，
            可参与 sandbox cwd 限制与 Foxtrail 路径裁决。
        SNAPSHOT: 支持状态快照（VersionedWorkspaceProvider.snapshot）。
        ROLLBACK: 支持回滚（VersionedWorkspaceProvider.rollback）。
        DIFF: 支持差异查看（VersionedWorkspaceProvider.diff）。
    """

    FILESYSTEM_BACKED = auto()
    SNAPSHOT = auto()
    ROLLBACK = auto()
    DIFF = auto()


class WorkspaceProvider(ABC):
    """Workspace 物理后端 provider 抽象基类。

    子类通过类变量声明身份与能力：
        - :attr:`provider_type`: provider 注册表分派键（如 "git"、"plain"）。
        - :attr:`capabilities`: capability 位组合。

    生命周期：init（创建/初始化）→ adopt（扫描认领已有目录）→ status（查询）
    → destroy（销毁）。
    """

    provider_type: ClassVar[str]
    capabilities: ClassVar[WorkspaceCaps]

    @abstractmethod
    async def init(self, record: WorkspaceRecord) -> None:
        """按 locator 初始化物理空间 + 写结构化 marker。

        幂等：locator 已存在且 marker 匹配（三要素一致）则认领式返回，不破坏
        现有内容；locator 不存在则按 provider 语义创建（如 git: mkdir + git init +
        initial commit；plain: mkdir）。

        Raises:
            ProviderError: 初始化失败（locator 冲突、不可写等）。
        """
        raise NotImplementedError

    @abstractmethod
    async def adopt(self, locator: str) -> AdoptResult | None:
        """扫描 locator，读 marker 校验三要素（workspace_id / provider_type /
        subject_id），匹配则返回可重建 WorkspaceRecord 的信息；无 marker 或
        不匹配返回 None（不误认领）。

        旧格式 marker（一行注释，不可机读）视为不可认领，返回 None（由调用方
        log 提示并提供 workspace_register 手动登记路径）。

        Args:
            locator: URI 形态定位（MVP file:///abs/path）。

        Returns:
            认领结果，或 None（无 marker / 不匹配 / 旧格式）。
        """
        raise NotImplementedError

    @abstractmethod
    async def status(self, record: WorkspaceRecord) -> WorkspaceStatus:
        """查询物理后端状态（存在性/可写性 + provider 自定义状态键）。"""
        raise NotImplementedError

    @abstractmethod
    async def destroy(self, record: WorkspaceRecord) -> None:
        """销毁物理空间（按 provider 语义，如递归删除目录）。"""
        raise NotImplementedError


class VersionedWorkspaceProvider(WorkspaceProvider, ABC):
    """带版本控制能力的 provider 窄化接口（git 等实现）。

    基类不假设版本能力；此接口在 :class:`WorkspaceProvider` 之上叠加
    snapshot/rollback/diff/list_snapshots。调用方按 ``isinstance`` 或
    capability 位（SNAPSHOT/ROLLBACK/DIFF）判定是否支持，不支持时返回
    CAPABILITY_NOT_SUPPORTED error，而非 AttributeError。
    """

    @abstractmethod
    async def snapshot(self, record: WorkspaceRecord, message: str = "") -> str:
        """创建状态快照，返回快照 id（如 git commit hash）。"""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self, record: WorkspaceRecord, snapshot_id: str) -> None:
        """回滚到指定快照（如 git checkout + git clean）。"""
        raise NotImplementedError

    @abstractmethod
    async def diff(self, record: WorkspaceRecord, snapshot_id: str | None = None) -> str:
        """获取 diff（与指定快照或工作区对比），返回 diff 文本。"""
        raise NotImplementedError

    @abstractmethod
    async def list_snapshots(
        self, record: WorkspaceRecord, max_count: int = 50
    ) -> list[SnapshotInfo]:
        """列出快照历史（最多 max_count 条）。"""
        raise NotImplementedError
