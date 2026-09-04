# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""v2 checkpoint 序列化与内存后端测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from _helpers import make_action_result, make_node

from ghrah.chat.message import ChatMessage
from ghrah.context import ContextManager, InMemoryBackend
from ghrah.context.persistence import (
    deserialize_action_result,
    deserialize_messages,
    deserialize_node,
    serialize_action_result,
    serialize_messages,
    serialize_node,
)


def test_action_result_roundtrip() -> None:
    """ActionResult 保留 outcome、data 与提示。"""
    result = make_action_result(data={"foo": "bar"}, hint="next")
    restored = deserialize_action_result(serialize_action_result(result))

    assert restored == result


def test_messages_roundtrip() -> None:
    """消息列表保留角色与文本。"""
    messages = [ChatMessage.system(text="system"), ChatMessage.user(text_or_blocks="hello")]
    restored = deserialize_messages(serialize_messages(messages))

    assert [message.role for message in restored] == ["system", "user"]
    assert [message.text for message in restored] == ["system", "hello"]


def test_node_roundtrip() -> None:
    """ContextNode v2 字段与内容可完整往返。"""
    node = make_node(
        timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        messages_delta=[ChatMessage.user(text_or_blocks="hello")],
        action_results=[{"ability_name": "tool", "action_result": make_action_result()}],
        metadata={"retry": True},
    )

    restored = deserialize_node(serialize_node(node))

    assert restored == node
    assert restored.session_id == node.session_id
    assert restored.created_on_branch_id == node.created_on_branch_id


@pytest.mark.asyncio
async def test_memory_checkpoint_roundtrip_is_isolated() -> None:
    """内存后端返回深拷贝，且按 Agent 隔离。"""
    backend = InMemoryBackend()
    manager = ContextManager(agent_name="agent-a", initial_state={"count": 0}, persistence=backend)
    manager.begin_iteration()
    manager.add_messages([ChatMessage.user(text_or_blocks="hello")])
    manager.apply_state_changes({"count": 1})
    manager.commit_iteration(ability_names=["chat"])
    await manager.persist()

    checkpoint = await backend.load_checkpoint("agent-a")
    assert checkpoint is not None
    assert len(checkpoint.nodes) == 2
    assert await backend.load_checkpoint("agent-b") is None
    assert await backend.list_agents() == ["agent-a"]


@pytest.mark.asyncio
async def test_memory_delete_checkpoint() -> None:
    """显式删除清理整个 Agent checkpoint。"""
    backend = InMemoryBackend()
    manager = ContextManager(agent_name="agent", persistence=backend)
    await manager.persist()

    await backend.delete_checkpoint("agent")

    assert await backend.load_checkpoint("agent") is None
    assert await backend.list_agents() == []


@pytest.mark.asyncio
async def test_context_manager_restores_state_messages_and_topology() -> None:
    """ContextManager 从 checkpoint 恢复 Head 派生的完整运行上下文。"""
    backend = InMemoryBackend()
    manager = ContextManager(agent_name="agent", initial_state={"step": 0}, persistence=backend)
    manager.begin_iteration()
    manager.add_messages([ChatMessage.user(text_or_blocks="one")])
    manager.apply_state_changes({"step": 1})
    manager.commit_iteration(ability_names=["work"])
    session_id = manager.active_session_id
    manager.create_branch(session_id=session_id, name="retry")
    await manager.persist()

    restored = ContextManager(agent_name="agent", persistence=backend)
    await restored.restore("agent")

    assert restored.get_current_state() == {"step": 1}
    assert [message.text for message in restored.message_store.current_messages] == ["one"]
    assert {branch.name for branch in restored.list_branches(session_id)} == {"main", "retry"}


@pytest.mark.asyncio
async def test_restore_without_checkpoint_fails() -> None:
    """不存在的 Agent 不产生隐式空 checkpoint。"""
    manager = ContextManager(agent_name="agent", persistence=InMemoryBackend())

    with pytest.raises(ValueError, match="No persisted data"):
        await manager.restore("missing")
