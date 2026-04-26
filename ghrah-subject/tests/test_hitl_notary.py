from __future__ import annotations

import asyncio

import pytest

from ghrah.subject.hitl.notary import HITLNotary
from ghrah.subject.hitl.policy import HITLPolicy, HITLVerdict


class TestHITLNotary:
    def test_check_request_auto_approved(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["read_file"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        verdict = notary.check_request("agent1", "read_file")
        assert verdict.approved is True
        assert verdict.reason == "auto_approved"

    def test_check_request_needs_approval(self) -> None:
        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)
        verdict = notary.check_request("agent1", "write_file")
        assert verdict.approved is False

    @pytest.mark.asyncio
    async def test_create_and_resolve_promise(self) -> None:
        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)

        promise = notary.create_promise("agent1", "write_file", {"file_path": "/tmp/test.txt"})
        assert promise.agent_name == "agent1"
        assert promise.ability_name == "write_file"
        assert promise.tool_args == {"file_path": "/tmp/test.txt"}
        assert not promise.future.done()

        verdict = HITLVerdict(approved=True, reason="observer_approved")
        result = notary.resolve_promise(promise.promise_id, verdict)
        assert result is True
        assert promise.future.done()
        assert promise.future.result().approved is True

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_promise(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        verdict = HITLVerdict(approved=True)
        result = notary.resolve_promise("nonexistent-id", verdict)
        assert result is False

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_promise(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        promise = notary.create_promise("agent1", "write_file")
        notary.resolve_promise(promise.promise_id, HITLVerdict(approved=True))

        result = notary.resolve_promise(
            promise.promise_id, HITLVerdict(approved=False)
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_promise(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        promise = notary.create_promise("agent1", "write_file")
        result = notary.reject_promise(promise.promise_id, "unsafe_operation")
        assert result is True
        assert promise.future.done()
        assert promise.future.result().approved is False
        assert promise.future.result().reason == "unsafe_operation"

    @pytest.mark.asyncio
    async def test_reject_promise_default_reason(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        promise = notary.create_promise("agent1", "write_file")
        notary.reject_promise(promise.promise_id)
        assert promise.future.result().reason == "rejected_by_observer"

    @pytest.mark.asyncio
    async def test_cancel_promise(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        promise = notary.create_promise("agent1", "write_file")
        result = notary.cancel_promise(promise.promise_id)
        assert result is True
        assert promise.future.cancelled()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_promise(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)
        result = notary.cancel_promise("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_all_promises(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        p1 = notary.create_promise("agent1", "write_file")
        p2 = notary.create_promise("agent1", "delete_file")
        p3 = notary.create_promise("agent2", "write_file")

        notary.cancel_all_promises(agent_name="agent1")
        assert p1.future.cancelled()
        assert p2.future.cancelled()
        assert not p3.future.done()

        pending = notary.list_pending_promises()
        assert len(pending) == 1
        assert pending[0].agent_name == "agent2"

    @pytest.mark.asyncio
    async def test_cancel_all_promises_no_filter(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        p1 = notary.create_promise("agent1", "write_file")
        p2 = notary.create_promise("agent2", "write_file")

        notary.cancel_all_promises()
        assert p1.future.cancelled()
        assert p2.future.cancelled()
        assert len(notary.list_pending_promises()) == 0

    @pytest.mark.asyncio
    async def test_list_pending_by_agent(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        notary.create_promise("agent1", "write_file")
        notary.create_promise("agent2", "delete_file")
        notary.create_promise("agent1", "edit_file")

        pending_agent1 = notary.list_pending_promises(agent_name="agent1")
        assert len(pending_agent1) == 2
        assert all(p.agent_name == "agent1" for p in pending_agent1)

        pending_all = notary.list_pending_promises()
        assert len(pending_all) == 3

    @pytest.mark.asyncio
    async def test_get_promise(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        promise = notary.create_promise("agent1", "write_file")
        found = notary.get_promise(promise.promise_id)
        assert found is promise

        not_found = notary.get_promise("nonexistent")
        assert not_found is None

    def test_policy_property(self) -> None:
        policy = HITLPolicy(auto_approve_abilities=["read_file"])
        notary = HITLNotary(policy)
        assert notary.policy is policy

    @pytest.mark.asyncio
    async def test_promise_id_uniqueness(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        p1 = notary.create_promise("agent1", "write_file")
        p2 = notary.create_promise("agent1", "write_file")
        assert p1.promise_id != p2.promise_id

    @pytest.mark.asyncio
    async def test_await_promise_resolution(self) -> None:
        policy = HITLPolicy()
        notary = HITLNotary(policy)

        promise = notary.create_promise("agent1", "write_file")

        async def resolve_later() -> None:
            await asyncio.sleep(0.01)
            notary.resolve_promise(
                promise.promise_id, HITLVerdict(approved=True, reason="ok")
            )

        asyncio.create_task(resolve_later())
        result = await promise.future
        assert result.approved is True
