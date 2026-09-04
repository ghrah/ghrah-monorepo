# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActionBranch：Session 内指向 Head 的稳定引用。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

__all__ = ["ActionBranch"]


@dataclass(frozen=True)
class ActionBranch:
    """Session 内的 Branch 元数据与 Head 引用。"""

    branch_id: str
    session_id: str
    name: str
    head_node_id: str
    parent_branch_id: str | None = None
    fork_point_node_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 Branch 标识与 fork 来源的不变量。"""
        if not self.branch_id:
            raise ValueError("branch_id must not be empty")
        if not self.session_id:
            raise ValueError("session_id must not be empty")
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.head_node_id:
            raise ValueError("head_node_id must not be empty")
        if (self.parent_branch_id is None) != (self.fork_point_node_id is None):
            raise ValueError(
                "parent_branch_id and fork_point_node_id must either both be set or both be None"
            )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def new_id(cls) -> str:
        """生成稳定 Branch ID。"""
        return uuid.uuid4().hex[:16]

    @classmethod
    def create_root(
        cls,
        *,
        session_id: str,
        head_node_id: str,
        name: str = "main",
        branch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """创建 Session 的默认 Root Branch。"""
        return cls(
            branch_id=branch_id or cls.new_id(),
            session_id=session_id,
            name=name,
            head_node_id=head_node_id,
            metadata=metadata or {},
        )

    @classmethod
    def create_fork(
        cls,
        *,
        session_id: str,
        name: str,
        head_node_id: str,
        parent_branch_id: str,
        fork_point_node_id: str,
        branch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """创建从同 Session 节点派生的 Branch。"""
        return cls(
            branch_id=branch_id or cls.new_id(),
            session_id=session_id,
            name=name,
            head_node_id=head_node_id,
            parent_branch_id=parent_branch_id,
            fork_point_node_id=fork_point_node_id,
            metadata=metadata or {},
        )

    @property
    def is_root(self) -> bool:
        """是否为 Session 的默认 Root Branch。"""
        return self.parent_branch_id is None
