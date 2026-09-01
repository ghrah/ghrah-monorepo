# SPDX-License-Identifier: Apache-2.0

"""Stage A lifecycle and Project-scoped Agent wire contracts."""

import pytest
from pydantic import ValidationError

from ghrah.protocol.types import (
    COMMAND_PAYLOAD_MAP,
    EVENT_PAYLOAD_MAP,
    ActionChainUpdatedPayload,
    ChainHistoryResultPayload,
    CommandType,
    EventType,
    GetChainHistoryPayload,
    ListAgentsPayload,
    ProjectDeletePayload,
    ProjectInfoPayload,
    ProjectLifecyclePayload,
    ProjectListPayload,
    RoomDeletePayload,
    RoomLifecyclePayload,
    SessionListPayload,
    SpawnAgentPayload,
    TerminateAgentPayload,
    WorkspaceStatusPayload,
    make_agent_key,
)


def test_lifecycle_payloads_are_versioned_and_mapped() -> None:
    project = ProjectLifecyclePayload(project_id="p1", expected_version=3)
    delete_project = ProjectDeletePayload(project_id="p1", expected_version=3)
    room = RoomLifecyclePayload(room_id="r1", expected_version=7)

    assert project.model_dump() == {"project_id": "p1", "expected_version": 3}
    assert delete_project.model_dump() == {
        "project_id": "p1",
        "expected_version": 3,
        "cascade_rooms": False,
    }
    assert RoomDeletePayload(room_id="r1", expected_version=7).model_dump() == room.model_dump()
    assert COMMAND_PAYLOAD_MAP[CommandType.PROJECT_ARCHIVE] is ProjectLifecyclePayload
    assert COMMAND_PAYLOAD_MAP[CommandType.PROJECT_RESTORE] is ProjectLifecyclePayload
    assert COMMAND_PAYLOAD_MAP[CommandType.ROOM_ARCHIVE] is RoomLifecyclePayload
    assert COMMAND_PAYLOAD_MAP[CommandType.ROOM_RESTORE] is RoomLifecyclePayload
    assert EVENT_PAYLOAD_MAP[EventType.PROJECT_ARCHIVED].__name__ == "ProjectEventPayload"
    assert EVENT_PAYLOAD_MAP[EventType.ROOM_RESTORED].__name__ == "RoomEventPayload"


def test_project_lifecycle_axes_and_legacy_deleted_record_input() -> None:
    assert ProjectListPayload().archived is False
    assert ProjectListPayload(archived=True).archived is True
    assert ProjectListPayload(archived=None).archived is None

    legacy = ProjectInfoPayload(
        project_id="p1",
        name="legacy",
        deleted_at="2026-08-27T00:00:00Z",
    )
    # A7 migration input remains readable. Stage C migrates deleted_at -> archived_at.
    assert legacy.deleted_at is not None
    assert legacy.archived_at is None
    assert legacy.status.value == "active"


@pytest.mark.parametrize(
    ("payload_cls", "payload"),
    [
        (SpawnAgentPayload, {"config": {"name": "a"}}),
        (ListAgentsPayload, {}),
        (TerminateAgentPayload, {"project_id": "p1", "name": "a"}),
        (GetChainHistoryPayload, {"project_id": "p1", "agent_name": "a"}),
        (SessionListPayload, {"project_id": "p1", "agent_name": "a"}),
        (WorkspaceStatusPayload, {"project_id": "p1", "agent_name": "a"}),
    ],
)
def test_new_agent_commands_reject_missing_stable_scope(payload_cls, payload) -> None:
    with pytest.raises(ValidationError):
        payload_cls.model_validate(payload)


def test_chain_result_carries_project_and_agent_identity() -> None:
    result = ChainHistoryResultPayload(
        project_id="p1",
        agent_id="a1",
        agent_name="architect",
    )
    assert result.model_dump()["project_id"] == "p1"
    assert result.model_dump()["agent_id"] == "a1"
    assert make_agent_key("p1", "a1") == "p1:a1"


def test_legacy_agent_event_is_accepted_without_guessing_scope() -> None:
    event = ActionChainUpdatedPayload(agent_name="legacy", node={})
    assert event.project_id == ""
    assert event.agent_id == ""
    assert event.cluster_id == ""
