# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActionSession 拓扑不变量校验。"""

from __future__ import annotations

from collections.abc import Iterable

from ghrah.context.action_session import ActionSession
from ghrah.context.branch import ActionBranch
from ghrah.context.node import ContextNode

__all__ = ["validate_session_topology"]


def validate_session_topology(
    session: ActionSession,
    branches: Iterable[ActionBranch],
    nodes: Iterable[ContextNode],
) -> None:
    """校验单 Session、单 Root、Branch Head 与节点引用闭合性。"""
    branch_by_id = {branch.branch_id: branch for branch in branches}
    node_by_id = {node.id: node for node in nodes}

    if session.active_branch_id not in branch_by_id:
        raise ValueError("active branch does not belong to the session")
    if session.root_node_id not in node_by_id:
        raise ValueError("root node does not belong to the session")

    roots = [node for node in node_by_id.values() if node.parent_id is None]
    if len(roots) != 1 or roots[0].id != session.root_node_id:
        raise ValueError("session must contain exactly one declared root")

    def ancestors(node_id: str) -> set[str]:
        """返回包含节点自身的祖先集，并检测环或断链。"""
        result: set[str] = set()
        current_id: str | None = node_id
        while current_id is not None:
            if current_id in result:
                raise ValueError("session node graph must not contain a cycle")
            result.add(current_id)
            current = node_by_id.get(current_id)
            if current is None:
                raise ValueError(f"node '{node_id}' has an unknown ancestor")
            current_id = current.parent_id
        if session.root_node_id not in result:
            raise ValueError(f"node '{node_id}' is not connected to the session root")
        return result

    for branch in branch_by_id.values():
        if branch.session_id != session.session_id:
            raise ValueError(f"branch '{branch.branch_id}' belongs to another session")
        if branch.head_node_id not in node_by_id:
            raise ValueError(f"branch '{branch.branch_id}' has an unknown head")
        if branch.parent_branch_id is not None:
            if branch.parent_branch_id not in branch_by_id:
                raise ValueError(f"branch '{branch.branch_id}' has an unknown parent branch")
            if branch.fork_point_node_id not in node_by_id:
                raise ValueError(f"branch '{branch.branch_id}' has an unknown fork point")

    for node in node_by_id.values():
        if node.session_id != session.session_id:
            raise ValueError(f"node '{node.id}' belongs to another session")
        if node.created_on_branch_id not in branch_by_id:
            raise ValueError(f"node '{node.id}' has an unknown creation branch")
        if node.parent_id is not None and node.parent_id not in node_by_id:
            raise ValueError(f"node '{node.id}' has an unknown parent")

    ancestors_by_branch = {
        branch.branch_id: ancestors(branch.head_node_id) for branch in branch_by_id.values()
    }
    for branch in branch_by_id.values():
        if branch.parent_branch_id is None or branch.fork_point_node_id is None:
            continue
        if branch.fork_point_node_id not in ancestors_by_branch[branch.branch_id]:
            raise ValueError(
                f"branch '{branch.branch_id}' head does not descend from its fork point"
            )
        if branch.fork_point_node_id not in ancestors_by_branch[branch.parent_branch_id]:
            raise ValueError(f"branch '{branch.branch_id}' fork point is outside its parent branch")

    for branch in branch_by_id.values():
        head = node_by_id[branch.head_node_id]
        if head.session_id != branch.session_id:
            raise ValueError(f"branch '{branch.branch_id}' head belongs to another session")
