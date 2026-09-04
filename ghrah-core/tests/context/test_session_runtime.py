# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""SessionRuntime 单 Root / 多 Branch 语义测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ghrah.context import ActionBranch, ActionSession, SessionRuntime


class TestSessionRuntime:
    """验证 Session 与 Branch 的稳定身份及拓扑语义。"""

    def test_create_builds_one_root_and_default_branch(self) -> None:
        """新 Session 原子创建 Root 和默认 Branch。"""
        runtime = SessionRuntime.create(
            agent_name="agent",
            system_prompt="system",
            agent_state={"step": 0},
            messages=["hello"],
            session_id="session-a",
            branch_id="branch-main",
        )

        assert runtime.session.session_id == "session-a"
        assert runtime.session.active_branch_id == "branch-main"
        assert runtime.active_branch.head_node_id == runtime.session.root_node_id
        assert runtime.active_head.parent_id is None
        assert runtime.active_head.session_id == "session-a"
        assert runtime.active_head.created_on_branch_id == "branch-main"

    def test_create_branch_only_adds_ref_and_does_not_activate(self) -> None:
        """Branch 创建只建立 Head 引用，不制造节点或隐式激活。"""
        runtime = SessionRuntime.create(
            agent_name="agent", session_id="session-a", branch_id="branch-main"
        )
        root_id = runtime.session.root_node_id

        branch = runtime.create_branch(name="retry-1", branch_id="branch-retry")

        assert runtime.chain.node_count == 1
        assert branch.head_node_id == root_id
        assert branch.fork_point_node_id == root_id
        assert runtime.session.active_branch_id == "branch-main"

    def test_branches_share_ancestors_and_advance_independently(self) -> None:
        """同 Session 的 Branch 共享祖先，Head 独立前移。"""
        runtime = SessionRuntime.create(
            agent_name="agent", session_id="session-a", branch_id="branch-main"
        )
        shared = runtime.commit_node(
            ability_names=["step"], agent_state={"step": 1}, messages_delta=["one"]
        )
        runtime.create_branch(
            name="retry-1",
            parent_branch_id="branch-main",
            fork_point_node_id=shared.id,
            branch_id="branch-retry",
        )

        main_node = runtime.commit_node(
            branch_id="branch-main", ability_names=["main"], agent_state={"path": "main"}
        )
        retry_node = runtime.commit_node(
            branch_id="branch-retry", ability_names=["retry"], agent_state={"path": "retry"}
        )

        assert runtime.get_branch("branch-main").head_node_id == main_node.id
        assert runtime.get_branch("branch-retry").head_node_id == retry_node.id
        assert [node.id for node in runtime.get_history("branch-main")] == [
            runtime.session.root_node_id,
            shared.id,
            main_node.id,
        ]
        assert [node.id for node in runtime.get_history("branch-retry")] == [
            runtime.session.root_node_id,
            shared.id,
            retry_node.id,
        ]

    def test_activate_branch_is_explicit(self) -> None:
        """创建后只有 activate_branch 会改变运行 Head。"""
        runtime = SessionRuntime.create(
            agent_name="agent", session_id="session-a", branch_id="branch-main"
        )
        runtime.create_branch(name="retry-1", branch_id="branch-retry")

        runtime.activate_branch("branch-retry")

        assert runtime.session.active_branch_id == "branch-retry"
        assert runtime.active_branch.name == "retry-1"

    def test_restore_rejects_cross_session_node(self) -> None:
        """恢复时禁止节点跨 Session 归属。"""
        runtime = SessionRuntime.create(
            agent_name="agent", session_id="session-a", branch_id="branch-main"
        )
        foreign_root = replace(runtime.active_head, session_id="session-b")

        with pytest.raises(ValueError, match="another session"):
            SessionRuntime.restore(
                session=runtime.session,
                branches=list(runtime.branches.values()),
                nodes=[foreign_root],
            )

    def test_restore_round_trip_preserves_active_branch(self) -> None:
        """重建后保留 Root、Branch Head 与激活指针。"""
        runtime = SessionRuntime.create(
            agent_name="agent", session_id="session-a", branch_id="branch-main"
        )
        runtime.create_branch(name="retry-1", branch_id="branch-retry")
        runtime.activate_branch("branch-retry")
        retry_head = runtime.commit_node(agent_state={"retry": True})

        restored = SessionRuntime.restore(
            session=runtime.session,
            branches=list(runtime.branches.values()),
            nodes=runtime.chain.nodes,
        )

        assert restored.session.root_node_id == runtime.session.root_node_id
        assert restored.session.active_branch_id == "branch-retry"
        assert restored.active_head.id == retry_head.id


def test_restore_rejects_disconnected_branch_head() -> None:
    """Branch Head 必须连通到 Session 声明的唯一 Root。"""
    runtime = SessionRuntime.create(
        agent_name="agent", session_id="session-a", branch_id="branch-main"
    )
    foreign_session = ActionSession.create(
        agent_name="agent",
        root_node_id=runtime.session.root_node_id,
        active_branch_id="branch-main",
        session_id="session-a",
    )
    bad_branch = ActionBranch.create_root(
        session_id="session-a",
        head_node_id="missing",
        branch_id="branch-main",
    )

    with pytest.raises(ValueError, match="unknown head"):
        SessionRuntime.restore(
            session=foreign_session,
            branches=[bad_branch],
            nodes=runtime.chain.nodes,
        )
