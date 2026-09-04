# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ContextNode 与单 Session ActionChain 契约测试。"""

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from ghrah.context.chain import ActionChain
from ghrah.context.node import ContextNode

SESSION_ID = "session-1"
BRANCH_ID = "branch-main"


def _node(**overrides) -> ContextNode:
    values = {
        "agent_name": "agent",
        "session_id": SESSION_ID,
        "created_on_branch_id": BRANCH_ID,
    }
    values.update(overrides)
    return ContextNode(**values)


class TestContextNode:
    def test_create_root(self) -> None:
        state = {"phase": "start"}
        messages = ["system"]
        root = ContextNode.create_root(
            "agent",
            state,
            messages,
            session_id=SESSION_ID,
            created_on_branch_id=BRANCH_ID,
        )
        assert root.parent_id is None
        assert root.iteration == 0
        assert root.ability_names == ["init"]
        assert root.agent_state == state
        assert root.messages_snapshot == messages
        assert root.is_snapshot
        assert root.session_id == SESSION_ID
        assert root.created_on_branch_id == BRANCH_ID

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("agent_name", "", "agent_name"),
            ("session_id", "", "session_id"),
            ("created_on_branch_id", "", "created_on_branch_id"),
        ],
    )
    def test_stable_scope_is_required(self, field: str, value: str, message: str) -> None:
        values = {
            "agent_name": "agent",
            "session_id": SESSION_ID,
            "created_on_branch_id": BRANCH_ID,
            field: value,
        }
        with pytest.raises(ValueError, match=message):
            ContextNode(**values)

    def test_is_frozen(self) -> None:
        node = _node()
        with pytest.raises(FrozenInstanceError):
            node.iteration = 2  # type: ignore[misc]

    def test_mutable_values_are_isolated(self) -> None:
        state = {"nested": {"count": 1}}
        metadata = {"tags": ["a"]}
        abilities = ["think"]
        node = _node(agent_state=state, metadata=metadata, ability_names=abilities)
        state["nested"]["count"] = 2
        metadata["tags"].append("b")
        abilities.append("write")
        assert node.agent_state == {"nested": {"count": 1}}
        assert node.metadata == {"tags": ["a"]}
        assert node.ability_names == ["think"]

    def test_generated_identity_and_timestamp(self) -> None:
        first = _node()
        second = _node()
        assert first.id != second.id
        assert isinstance(first.timestamp, datetime)


class TestActionChain:
    def _chain(self) -> tuple[ActionChain, ContextNode]:
        chain = ActionChain("agent", SESSION_ID)
        root = chain.init_chain(branch_id=BRANCH_ID, agent_state={"step": 0})
        return chain, root

    def test_init_creates_one_root(self) -> None:
        chain, root = self._chain()
        assert chain.nodes == [root]
        assert chain.node_count == 1
        with pytest.raises(ValueError, match="already initialized"):
            chain.init_chain(branch_id=BRANCH_ID)

    def test_append_and_history(self) -> None:
        chain, root = self._chain()
        first = chain.append_node(
            parent_id=root.id,
            branch_id=BRANCH_ID,
            ability_names=["think"],
            agent_state={"step": 1},
        )
        second = chain.append_node(
            parent_id=first.id,
            branch_id=BRANCH_ID,
            ability_names=["write"],
            agent_state={"step": 2},
        )
        assert [node.id for node in chain.get_history_from(second.id)] == [
            root.id,
            first.id,
            second.id,
        ]
        assert chain.get_history_from(second.id, limit=1) == [second]
        assert second.iteration == 2

    def test_append_rejects_unknown_parent_and_empty_branch(self) -> None:
        chain, root = self._chain()
        with pytest.raises(ValueError, match="not found"):
            chain.append_node(parent_id="missing", branch_id=BRANCH_ID)
        with pytest.raises(ValueError, match="branch_id"):
            chain.append_node(parent_id=root.id, branch_id="")

    def test_ingest_validates_ownership_and_duplicates(self) -> None:
        chain = ActionChain("agent", SESSION_ID)
        node = _node()
        chain.ingest_node(node)
        assert chain.checkout(node.id) is node
        with pytest.raises(ValueError, match="already exists"):
            chain.ingest_node(node)
        with pytest.raises(ValueError, match="another session"):
            chain.ingest_node(_node(session_id="other"))

    def test_constructor_requires_stable_scope(self) -> None:
        with pytest.raises(ValueError, match="agent_name"):
            ActionChain("", SESSION_ID)
        with pytest.raises(ValueError, match="session_id"):
            ActionChain("agent", "")
