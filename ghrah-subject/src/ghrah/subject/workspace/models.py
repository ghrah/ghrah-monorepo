# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace 资源模型：Subject 级一等资源（不含 project 维度）。

WorkspaceRecord 是 workspace 的持久化主键身份与定位信息，与物理后端解耦：
- 身份/定位/时间戳在此模型；
- 物理 git/plain/NFS/数据表后端的 init/adopt/status/destroy 由 provider 分派。

WorkspaceRecord 不持 project_id——project 与 workspace 的 1:N
挂载关系由 ProjectRecord.workspaces 表达（Stage B），本注册表对 project 无感知。

locator 用 URI 形态（MVP 仅 file:///abs/path），不假设文件系统：非文件系统后端
（nfs://、table://）的 grant subpath 语义由 provider 自定义（MVP 不实现，模型不堵死）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

__all__ = [
    "WorkspaceRecord",
    "WorkspaceStatus",
    "AdoptResult",
    "SnapshotInfo",
]


def _now() -> datetime:
    return datetime.now(UTC)


class WorkspaceRecord(BaseModel):
    """单个 Workspace 的 Subject 级资源记录。

    Attributes:
        workspace_id: 持久化主键，全局唯一（uuid4().hex）。
        name: 人类可读名称，可重复。
        provider_type: provider 注册表分派键，如 "git" | "plain"
            （注册表开放扩展，不用 enum 封闭；其他 VCS/NFS/数据表未来接入）。
        locator: URI 形态定位，如 "file:///abs/path"。
            FILESYSTEM_BACKED provider 的 locator 必为 file:// 且可解析出本地路径。
        subject_id: 认领归属（防误认领其他 subject 的目录）；MVP 默认 "default"。
        created_at / updated_at: 时间戳（内部 datetime(UTC)，序列化为 ISO str）。
        deleted_at: 软删时间戳，None 表示未删。
    """

    model_config = ConfigDict(from_attributes=True)

    workspace_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    provider_type: str
    locator: str
    subject_id: str = "default"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    deleted_at: datetime | None = None

    @field_serializer("created_at", "updated_at", "deleted_at")
    def _ser_dt(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @field_validator("created_at", "updated_at", "deleted_at", mode="before")
    @classmethod
    def _coerce_dt(cls, value: Any) -> Any:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value


class WorkspaceStatus(BaseModel):
    """Workspace 物理后端状态（provider.status 返回）。

    公共分母只含存在性/可写性；git 等带版本能力的 provider 在此基础上扩展脏文件
    计数等（见 :class:`ghrah.subject.sandbox.workspace.WorkspaceStatus` 旧形态，
    本模型为 provider 层通用基座，不假设版本能力字段）。

    Attributes:
        exists: locator 指向的物理空间是否存在。
        writable: 是否可写。
        extra: provider 自定义状态键（如 git 的 branch/is_clean/脏文件计数），
            不强约束 schema，由 provider 填充、调用方按 capability 解读。
    """

    model_config = ConfigDict(from_attributes=True)

    exists: bool
    writable: bool
    extra: dict[str, Any] = Field(default_factory=dict)


class AdoptResult(BaseModel):
    """provider.adopt 的认领结果。

    provider 扫描 locator，读 marker 校验三要素（workspace_id / provider_type /
    subject_id）后返回可重建 :class:`WorkspaceRecord` 的信息；无 marker 或不匹配
    返回 None（见 :meth:`WorkspaceProvider.adopt`）。

    Attributes:
        workspace_id: marker 中的 workspace_id（认领主键）。
        provider_type: marker 中的 provider_type（与探测一致才认领）。
        subject_id: marker 中的 subject_id（与目标 subject 一致才认领）。
        name: 认领时采用的人类可读名（默认从 locator 路径末段推断或 agent_name）。
        created_at: marker 中的创建时间（ISO str），无则 None。
    """

    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    provider_type: str
    subject_id: str
    name: str = ""
    created_at: str | None = None


class SnapshotInfo(BaseModel):
    """快照信息（VersionedWorkspaceProvider.list_snapshots 返回项）。"""

    model_config = ConfigDict(from_attributes=True)

    commit_hash: str
    message: str
    timestamp: float
