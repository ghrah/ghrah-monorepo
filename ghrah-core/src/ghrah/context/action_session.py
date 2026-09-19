# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActionSession：拥有独立 ActionChain Root 的执行会话。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

__all__ = ["ActionSession"]


@dataclass(frozen=True)
class ActionSession:
    """Agent 的独立 Root 执行上下文。"""

    session_id: str
    agent_name: str
    name: str
    root_node_id: str
    active_branch_id: str
    lifecycle: str = "open"
    system_prompt: str = ""
    origin_agent_name: str | None = None
    origin_session_id: str | None = None
    origin_node_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 Session 的 Root、命名与来源不变量。"""
        if not self.session_id:
            raise ValueError("session_id must not be empty")
        if not self.agent_name:
            raise ValueError("agent_name must not be empty")
        if not self.name or not self.name.strip():
            raise ValueError("name must be a non-empty trimmed string")
        if not self.root_node_id:
            raise ValueError("root_node_id must not be empty")
        if not self.active_branch_id:
            raise ValueError("active_branch_id must not be empty")
        if self.lifecycle not in ("open", "archived", "deleted"):
            raise ValueError(f"invalid lifecycle: {self.lifecycle}")
        origin_fields = (self.origin_agent_name, self.origin_session_id, self.origin_node_id)
        if any(value is None for value in origin_fields) and any(
            value is not None for value in origin_fields
        ):
            raise ValueError(
                "origin_agent_name, origin_session_id and origin_node_id must either "
                "all be set or all be None"
            )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def new_id(cls) -> str:
        """生成稳定 Session ID。"""
        return uuid.uuid4().hex[:16]

    @classmethod
    def create(
        cls,
        *,
        agent_name: str,
        name: str,
        root_node_id: str,
        active_branch_id: str,
        session_id: str | None = None,
        lifecycle: str = "open",
        system_prompt: str = "",
        origin_agent_name: str | None = None,
        origin_session_id: str | None = None,
        origin_node_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """创建独立 Root Session。"""
        return cls(
            session_id=session_id or cls.new_id(),
            agent_name=agent_name,
            name=name.strip(),
            root_node_id=root_node_id,
            active_branch_id=active_branch_id,
            lifecycle=lifecycle,
            system_prompt=system_prompt,
            origin_agent_name=origin_agent_name,
            origin_session_id=origin_session_id,
            origin_node_id=origin_node_id,
            metadata=metadata or {},
        )

    @property
    def is_derived(self) -> bool:
        """是否基于另一 Session 的节点创建。"""
        return self.origin_session_id is not None
