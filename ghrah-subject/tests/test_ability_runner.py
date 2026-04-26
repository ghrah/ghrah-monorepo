from __future__ import annotations

import asyncio

import pytest
from ghrah.abilities import AbilityRegistry, ActionOutcome, ActionResult
from ghrah.abilities.base import Ability
from ghrah.abilities.context import AbilityExecutionContext

from ghrah.subject.ability_runner import AbilityRunner, AbilityRunnerConfig
from ghrah.subject.hitl.notary import HITLNotary
from ghrah.subject.hitl.policy import HITLPolicy, HITLVerdict
from ghrah.subject.permission_checker import PermissionChecker


class _DummyAbility(Ability):
    @property
    def name(self) -> str:
        return "dummy_test_ability"

    async def execute(self, context: AbilityExecutionContext) -> ActionResult:
        return ActionResult(
            outcome=ActionOutcome.SUCCESS,
            data={"message": "dummy executed"},
        )

    def get_hooks(self) -> list:
        return []


class _FailAbility(Ability):
    @property
    def name(self) -> str:
        return "fail_test_ability"

    async def execute(self, context: AbilityExecutionContext) -> ActionResult:
        return ActionResult(
            outcome=ActionOutcome.FAILURE,
            data={"error": "intentional failure"},
        )

    def get_hooks(self) -> list:
        return []


class _EchoAbility(Ability):
    @property
    def name(self) -> str:
        return "echo_test_ability"

    async def execute(self, context: AbilityExecutionContext) -> ActionResult:
        return ActionResult(
            outcome=ActionOutcome.SUCCESS,
            data={"echo": context.tool_args},
        )

    def get_hooks(self) -> list:
        return []


@pytest.fixture(autouse=True)
def _register_test_abilities() -> None:
    AbilityRegistry.register("dummy_test_ability", _DummyAbility)
    AbilityRegistry.register("fail_test_ability", _FailAbility)
    AbilityRegistry.register("echo_test_ability", _EchoAbility)


class TestAbilityRunnerExecuteAbility:
    async def test_execute_known_ability(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["dummy_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        result = await runner.execute_ability(
            ability_name="dummy_test_ability",
            tool_args={},
            agent_name="test_agent",
        )
        assert result.outcome == ActionOutcome.SUCCESS
        assert result.data["message"] == "dummy executed"

    async def test_execute_unknown_ability_returns_failure(self) -> None:
        policy = HITLPolicy(require_approval_by_default=False)
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        result = await runner.execute_ability(
            ability_name="nonexistent_ability",
            tool_args={},
            agent_name="test_agent",
        )
        assert result.outcome == ActionOutcome.FAILURE
        assert "Ability not found" in result.data["error"]

    async def test_execute_ability_echoes_tool_args(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["echo_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        tool_args = {"key": "value", "number": 42}
        result = await runner.execute_ability(
            ability_name="echo_test_ability",
            tool_args=tool_args,
            agent_name="test_agent",
        )
        assert result.outcome == ActionOutcome.SUCCESS
        assert result.data["echo"] == tool_args

    async def test_execute_ability_failure_result(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["fail_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        result = await runner.execute_ability(
            ability_name="fail_test_ability",
            tool_args={},
            agent_name="test_agent",
        )
        assert result.outcome == ActionOutcome.FAILURE
        assert result.data["error"] == "intentional failure"


class TestAbilityRunnerPermissionCheck:
    async def test_permission_deny_blocks_execution(self) -> None:
        policy = HITLPolicy(require_approval_by_default=False)
        notary = HITLNotary(policy)
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"],
            require_approval=False,
        )
        runner = AbilityRunner(hitl_notary=notary, permission_checker=checker)

        result = await runner.execute_ability(
            ability_name="read_file",
            tool_args={"file_path": "/etc/passwd"},
            agent_name="test_agent",
        )
        assert result.outcome == ActionOutcome.FAILURE
        assert "Permission denied" in result.data["error"]

    async def test_permission_allow_executes(self) -> None:
        policy = HITLPolicy(require_approval_by_default=False)
        notary = HITLNotary(policy)
        checker = PermissionChecker(
            allowed_paths=["/tmp/safe"],
        )
        runner = AbilityRunner(hitl_notary=notary, permission_checker=checker)

        result = await runner.execute_ability(
            ability_name="echo_test_ability",
            tool_args={"file_path": "/tmp/safe/file.txt"},
            agent_name="test_agent",
        )
        assert result.outcome == ActionOutcome.SUCCESS


class TestAbilityRunnerHITL:
    async def test_hitl_approved_execution(self) -> None:
        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        async def approve_after_promise() -> None:
            for _ in range(50):
                await asyncio.sleep(0.01)
                pending = notary.list_pending_promises(agent_name="test_agent")
                if pending:
                    notary.resolve_promise(
                        pending[0].promise_id,
                        HITLVerdict(approved=True, reason="approved"),
                    )
                    return

        task = asyncio.create_task(approve_after_promise())
        result = await runner.execute_ability(
            ability_name="dummy_test_ability",
            tool_args={},
            agent_name="test_agent",
        )
        await task
        assert result.outcome == ActionOutcome.SUCCESS

    async def test_hitl_rejected_execution(self) -> None:
        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        async def reject_after_promise() -> None:
            for _ in range(50):
                await asyncio.sleep(0.01)
                pending = notary.list_pending_promises(agent_name="test_agent")
                if pending:
                    notary.reject_promise(pending[0].promise_id, "unsafe")
                    return

        task = asyncio.create_task(reject_after_promise())
        result = await runner.execute_ability(
            ability_name="dummy_test_ability",
            tool_args={},
            agent_name="test_agent",
        )
        await task
        assert result.outcome == ActionOutcome.FAILURE
        assert "HITL rejected" in result.data["error"]

    async def test_hitl_timeout_rejection(self) -> None:
        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)
        config = AbilityRunnerConfig(hitl_timeout=0.05)
        runner = AbilityRunner(hitl_notary=notary, config=config)

        result = await runner.execute_ability(
            ability_name="dummy_test_ability",
            tool_args={},
            agent_name="test_agent",
        )
        assert result.outcome == ActionOutcome.FAILURE
        assert "HITL" in result.data["error"]


class TestAbilityRunnerExecuteToolCalls:
    async def test_execute_tool_calls_single(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["echo_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        tool_calls = [
            {
                "name": "echo_test_ability",
                "args": {"key": "value"},
                "id": "call_1",
            }
        ]
        results = await runner.execute_tool_calls(
            tool_calls=tool_calls,
            agent_name="test_agent",
        )
        assert len(results) == 1
        assert results[0]["ability_name"] == "echo_test_ability"
        assert results[0]["action_result"].outcome == ActionOutcome.SUCCESS
        assert results[0]["tool_call_id"] == "call_1"

    async def test_execute_tool_calls_multiple(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["echo_test_ability", "dummy_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        tool_calls = [
            {
                "name": "echo_test_ability",
                "args": {"key": "1"},
                "id": "call_1",
            },
            {
                "name": "dummy_test_ability",
                "args": {},
                "id": "call_2",
            },
        ]
        results = await runner.execute_tool_calls(
            tool_calls=tool_calls,
            agent_name="test_agent",
        )
        assert len(results) == 2
        outcomes = [r["action_result"].outcome for r in results]
        assert ActionOutcome.SUCCESS in outcomes

    async def test_execute_tool_calls_string_args(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["echo_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        tool_calls = [
            {
                "name": "echo_test_ability",
                "args": '{"key": "parsed"}',
                "id": "call_str",
            }
        ]
        results = await runner.execute_tool_calls(
            tool_calls=tool_calls,
            agent_name="test_agent",
        )
        assert len(results) == 1
        assert results[0]["action_result"].outcome == ActionOutcome.SUCCESS

    async def test_execute_tool_calls_invalid_json_args(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["echo_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        tool_calls = [
            {
                "name": "echo_test_ability",
                "args": "not valid json",
                "id": "call_invalid",
            }
        ]
        results = await runner.execute_tool_calls(
            tool_calls=tool_calls,
            agent_name="test_agent",
        )
        assert len(results) == 1
        assert results[0]["action_result"].outcome == ActionOutcome.SUCCESS
        assert results[0]["action_result"].data["echo"] == {}

    async def test_execute_tool_calls_function_format(self) -> None:
        policy = HITLPolicy(
            auto_approve_abilities=["echo_test_ability"],
            require_approval_by_default=True,
        )
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        tool_calls = [
            {
                "function": {"name": "echo_test_ability"},
                "arguments": {"key": "from_function"},
                "id": "call_fn",
            }
        ]
        results = await runner.execute_tool_calls(
            tool_calls=tool_calls,
            agent_name="test_agent",
        )
        assert len(results) == 1
        assert results[0]["action_result"].outcome == ActionOutcome.SUCCESS


class TestAbilityRunnerConfig:
    def test_default_config(self) -> None:
        config = AbilityRunnerConfig()
        assert config.hitl_timeout is None
        assert config.default_ability_timeout == 300.0

    def test_custom_config(self) -> None:
        config = AbilityRunnerConfig(hitl_timeout=60.0, default_ability_timeout=120.0)
        assert config.hitl_timeout == 60.0
        assert config.default_ability_timeout == 120.0
