# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ContextChanges：持久化层的最小增量变更集。"""

from __future__ import annotations

from dataclasses import dataclass

from ghrah.context.action_session import ActionSession
from ghrah.context.branch import ActionBranch
from ghrah.context.node import ContextNode

__all__ = ["ContextChanges"]


@dataclass(frozen=True)
class ContextChanges:
    """一个 Agent 的原子增量持久化变更。"""

    agent_name: str
    sessions: tuple[ActionSession, ...] = ()
    branches: tuple[ActionBranch, ...] = ()
    nodes: tuple[ContextNode, ...] = ()
    active_session_id: str | None = None
    delete_session_ids: tuple[str, ...] = ()
    delete_branch_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验变更集的 Agent 所有权与 ID 唯一性。"""
        if not self.agent_name:
            raise ValueError("agent_name must not be empty")
        if any(session.agent_name != self.agent_name for session in self.sessions):
            raise ValueError("changes contain a session owned by another agent")
        if any(node.agent_name != self.agent_name for node in self.nodes):
            raise ValueError("changes contain a node owned by another agent")
        groups = (
            [session.session_id for session in self.sessions],
            [branch.branch_id for branch in self.branches],
            [node.id for node in self.nodes],
            list(self.delete_session_ids),
            list(self.delete_branch_ids),
        )
        if any(len(values) != len(set(values)) for values in groups):
            raise ValueError("changes contain duplicate IDs")
