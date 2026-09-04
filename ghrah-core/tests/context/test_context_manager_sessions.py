# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ContextManager 真多 Session / Branch 运行时测试。"""

from __future__ import annotations

import pytest

from ghrah.chat.factory import ChatMessageFactory
from ghrah.chat.message import ChatMessage
from ghrah.context import ContextManager, InMemoryBackend


def _manager(*, persistence: InMemoryBackend | None = None) -> ContextManager:
    return ContextManager(
        agent_name="agent",
        initial_state={"path": "main"},
        message_factory=ChatMessageFactory(),
        persistence=persistence,
    )


def _commit(cm: ContextManager, text: str, path: str) -> None:
    cm.begin_iteration()
    cm.add_messages([ChatMessage.user(text_or_blocks=text)])
    cm.apply_state_changes({"path": path})
    cm.commit_iteration(ability_names=[path])


def test_session_create_builds_independent_root_without_activation() -> None:
    """新建 Session 拥有新 Root，且不会抢占运行态。"""
    cm = _manager()
    original_session_id = cm.active_session_id
    original_root_id = cm.get_active_session().root_node_id

    created = cm.create_session(initial_state={"path": "new"})

    assert cm.active_session_id == original_session_id
    assert created.root_node_id != original_root_id
    assert cm.get_branch_head(created.session_id, created.active_branch_id).parent_id is None


def test_session_activate_restores_state_and_messages() -> None:
    """Session 激活完整恢复 Head 的 state 和 messages。"""
    cm = _manager()
    main_session_id = cm.active_session_id
    _commit(cm, "main-message", "main-committed")
    created = cm.create_session(
        initial_state={"path": "other"},
        initial_messages=[ChatMessage.user(text_or_blocks="other-message")],
    )

    cm.activate_session(created.session_id)
    assert cm.get_current_state() == {"path": "other"}
    assert [message.text for message in cm.message_store.current_messages] == ["other-message"]

    cm.activate_session(main_session_id)
    assert cm.get_current_state() == {"path": "main-committed"}
    assert [message.text for message in cm.message_store.current_messages] == ["main-message"]


def test_derived_session_copies_context_without_cross_session_parent() -> None:
    """基于节点新建 Session 只记录来源，Root 不跨 Session 连边。"""
    cm = _manager()
    _commit(cm, "source-message", "source")
    source_session_id = cm.active_session_id
    source_node_id = cm.active_head.id

    derived = cm.create_session(
        origin_session_id=source_session_id,
        origin_node_id=source_node_id,
    )
    root = cm.get_branch_head(derived.session_id, derived.active_branch_id)

    assert root.parent_id is None
    assert root.agent_state == {"path": "source"}
    assert derived.origin_session_id == source_session_id
    assert derived.origin_node_id == source_node_id
    assert [message.text for message in cm.get_messages(session_id=derived.session_id)] == [
        "source-message"
    ]


def test_branch_create_and_activate_restore_fork_point_context() -> None:
    """Branch 创建与激活分离，激活后恢复 fork point 上下文。"""
    cm = _manager()
    session_id = cm.active_session_id
    main_branch_id = cm.get_active_session().active_branch_id
    _commit(cm, "shared", "shared")
    fork_point = cm.active_head
    retry = cm.create_branch(
        session_id=session_id,
        name="retry-1",
        from_node_id=fork_point.id,
        parent_branch_id=main_branch_id,
    )
    _commit(cm, "main-only", "main-after")

    assert cm.get_active_session().active_branch_id == main_branch_id
    cm.activate_branch(session_id, retry.branch_id)
    assert cm.get_current_state() == {"path": "shared"}
    assert [message.text for message in cm.message_store.current_messages] == ["shared"]


def test_activation_is_forbidden_during_iteration() -> None:
    """迭代事务中不允许改变 Session/Branch Head。"""
    cm = _manager()
    created = cm.create_session(initial_state={})
    cm.begin_iteration()

    with pytest.raises(RuntimeError, match="during an iteration"):
        cm.activate_session(created.session_id)

    cm.rollback_iteration(RuntimeError("cleanup"))


def test_deleted_session_cannot_be_activated_or_extended() -> None:
    """Session 墓碑不可再次进入运行态或创建新 Branch。"""
    cm = _manager()
    deleted = cm.create_session(initial_state={})
    cm.delete_session(deleted.session_id)

    with pytest.raises(ValueError, match="deleted session"):
        cm.activate_session(deleted.session_id)
    with pytest.raises(ValueError, match="deleted session"):
        cm.create_branch(session_id=deleted.session_id, name="retry")


@pytest.mark.asyncio
async def test_memory_checkpoint_restores_multiple_sessions_and_active_context() -> None:
    """内存 checkpoint 往返后恢复多 Root 与 active Session/Branch。"""
    backend = InMemoryBackend()
    cm = _manager(persistence=backend)
    _commit(cm, "main", "main")
    created = cm.create_session(
        initial_state={"path": "other"},
        initial_messages=[ChatMessage.user(text_or_blocks="other")],
    )
    cm.activate_session(created.session_id)
    retry = cm.create_branch(session_id=created.session_id, name="retry-1")
    cm.activate_branch(created.session_id, retry.branch_id)
    await cm.persist()

    restored = _manager(persistence=backend)
    await restored.restore("agent")

    assert len(restored.list_sessions()) == 2
    assert restored.active_session_id == created.session_id
    assert restored.get_active_session().active_branch_id == retry.branch_id
    assert restored.get_current_state() == {"path": "other"}
    assert [message.text for message in restored.message_store.current_messages] == ["other"]


@pytest.mark.asyncio
async def test_auto_persist_commit_emits_constant_size_changes() -> None:
    """多次 commit 每次只写一个 Node 和一个 Branch Head。"""

    class RecordingBackend(InMemoryBackend):
        def __init__(self) -> None:
            super().__init__()
            self.change_sizes: list[tuple[int, int, int]] = []

        async def apply_changes(self, changes) -> None:
            self.change_sizes.append(
                (len(changes.sessions), len(changes.branches), len(changes.nodes))
            )
            await super().apply_changes(changes)

    backend = RecordingBackend()
    cm = ContextManager(
        agent_name="agent",
        message_factory=ChatMessageFactory(),
        persistence=backend,
        auto_persist=True,
    )
    await cm.wait_for_persist()
    backend.change_sizes.clear()

    for index in range(20):
        cm.begin_iteration()
        cm.commit_iteration(ability_names=[f"step-{index}"])
    await cm.wait_for_persist()

    assert backend.change_sizes == [(0, 1, 1)] * 20
