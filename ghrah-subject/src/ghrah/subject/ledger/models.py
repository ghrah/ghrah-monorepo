from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ghrah.context.node import ContextNode
from ghrah.context.persistence import deserialize_node, serialize_node
from pydantic import BaseModel, Field

__all__ = ["LedgerNode", "ChainMeta", "DAGEntry"]


class LedgerNode(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    parent_id: str | None = None
    agent_name: str = ""
    session_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    iteration: int = 0
    ability_names: list[str] = Field(default_factory=list)
    agent_state: dict[str, Any] = Field(default_factory=dict)
    messages_delta: list[Any] = Field(default_factory=list)
    messages_snapshot: list[Any] | None = None
    is_snapshot: bool = False
    action_results: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    branch_name: str = "main"

    @classmethod
    def from_context_node(cls, node: ContextNode) -> LedgerNode:
        serialized = serialize_node(node)
        return cls.model_validate(serialized)

    def to_context_node(self) -> ContextNode:
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        return deserialize_node(data)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ChainMeta(BaseModel):
    model_config = {"from_attributes": True}

    agent_name: str
    branches: dict[str, str] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    active_session_id: str = ""


class DAGEntry(BaseModel):
    model_config = {"from_attributes": True}

    node: LedgerNode
    children: list[str] = Field(default_factory=list)
    depth: int = 0
