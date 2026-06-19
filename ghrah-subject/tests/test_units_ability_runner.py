from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from ghrah.abilities import AbilityRegistry, ActionOutcome, ActionResult
from ghrah.abilities.base import Ability
from ghrah.abilities.context import AbilityExecutionContext

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SUBJECT_HITL_REQUEST_CREATED
from ghrah.subject.hitl.policy import HITLVerdict
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.runtime.service_keys import ABILITY_EXECUTOR, SANDBOX_EXECUTOR
from ghrah.subject.unit.base import CommandContext
from ghrah.subject.units.ability_runner import AbilityRunnerUnit

# ── Test ability fixtures ───────────────────────────────────────────────────


class _AutoAbility(Ability):
    @property
    def name(self) -> str:
        return "unit_auto_ability"

    async def execute(self, context: AbilityExecutionContext) -> ActionResult:
        return ActionResult(
            outcome=ActionOutcome.SUCCESS,
            data={"ran": True, "args": context.tool_args},
        )

    def get_hooks(self) -> list[Any]:
        return []


class _FailAbility(Ability):
    @property
    def name(self) -> str:
        return "unit_fail_ability"

    async def execute(self, context: AbilityExecutionContext) -> ActionResult:
        return ActionResult(
            outcome=ActionOutcome.FAILURE,
            data={"error": "boom"},
        )

    def get_hooks(self) -> list[Any]:
        return []


@pytest.fixture(autouse=True)
def _register_test_abilities() -> None:
    AbilityRegistry.register("unit_auto_ability", _AutoAbility)
    AbilityRegistry.register("unit_fail_ability", _FailAbility)


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


# ── Meta / registration ─────────────────────────────────────────────────────


def test_ability_runner_unit_meta_declares_requires_and_long_running_only() -> None:
    unit = AbilityRunnerUnit(SubjectConfig())

    assert unit.meta.name == "ability_runner"
    assert unit.meta.routes.long_running_commands == frozenset({"execute_ability"})
    # D10：不与 commands 重复
    assert unit.meta.routes.commands == frozenset()
    assert unit.meta.routes.long_running_commands.isdisjoint(unit.meta.routes.commands)
    key_names = {k.name for k in unit.meta.requires}
    assert key_names == {
        "hitl_notary",
        "permission_service",
        "workspace_service",
        "sandbox_executor",
    }
    assert ABILITY_EXECUTOR in unit.meta.provides


def test_register_builtin_units_coexistence_includes_ability_runner() -> None:
    engine = SubjectEngine(SubjectConfig())
    engine.register_builtin_units(profile="coexistence")

    unit = engine.get_unit("ability_runner")
    assert isinstance(unit, AbilityRunnerUnit)


# ── Init / borrowing ────────────────────────────────────────────────────────


async def test_ability_runner_unit_init_injects_workspace_event_bus_and_sandbox(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("ability_runner")
        assert isinstance(unit, AbilityRunnerUnit)

        # Service registered under ABILITY_EXECUTOR
        assert engine.context.services.require(ABILITY_EXECUTOR) is unit.service

        # D4 新路径注入：workspace typed service + event_bus + sandbox_executor
        assert unit.service._workspace is not None
        assert unit.service._event_bus is engine.event_bus
        assert unit.service._sandbox_executor is engine.services.require(SANDBOX_EXECUTOR)

        # S2.4：legacy bind_* 回调已移除，不再有 _on_hitl_promise_created/_workspace_resolver
        assert not hasattr(unit.service, "_on_hitl_promise_created")
        assert not hasattr(unit.service, "_workspace_resolver")
        assert not hasattr(unit.service, "bind_hitl_broadcast")
        assert not hasattr(unit.service, "bind_workspace_resolver")
    finally:
        await engine.stop()


# ── handle_command ──────────────────────────────────────────────────────────


async def test_handle_command_unknown_returns_failure(tmp_path: Path) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("ability_runner")
        assert isinstance(unit, AbilityRunnerUnit)

        result = await unit.handle_command(
            "not_execute_ability",
            {},
            CommandContext.core("req-x"),
        )
        assert result == {
            "success": False,
            "error": "Unknown ability command: not_execute_ability",
        }
    finally:
        await engine.stop()


# ── D4 new path: auto-approved ability executes end-to-end via manifest ─────


AUTO_ABILITY_YAML = """\
manifest: ability
version: "1"
metadata:
  namespace: custom
  name: unit_auto
  description: auto-approved ability for unit test
  permissions:
    require_hitl: false
tool:
  name: unit_auto_ability
  description: auto-approved ability for unit test
  parameters: {}
implementation:
  type: builtin
  handler: unit_auto_ability
"""


async def test_handle_command_auto_approved_ability_succeeds_via_new_path(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        manifest_store = engine.get_unit("manifest_store")
        assert manifest_store is not None
        put = await manifest_store.handle_command(
            "manifest_put_ability",
            {"full_name": "custom.unit_auto", "content": AUTO_ABILITY_YAML},
            CommandContext.observer("req-m", session_id=None),
        )
        assert put["success"] is True

        unit = engine.get_unit("ability_runner")
        assert isinstance(unit, AbilityRunnerUnit)

        result = await unit.handle_command(
            "execute_ability",
            {
                "request_id": "req-2",
                "agent_name": "agent-a",
                "ability_name": "unit_auto_ability",
                "tool_args": {"k": "v"},
            },
            CommandContext.core("req-2"),
        )
        assert result["success"] is True
        assert result["request_id"] == "req-2"
        assert result["result"] == {"ran": True, "args": {"k": "v"}}
        assert result["error"] is None
    finally:
        await engine.stop()


async def test_handle_command_failure_ability_returns_error(tmp_path: Path) -> None:
    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        manifest_store = engine.get_unit("manifest_store")
        assert manifest_store is not None
        fail_yaml = AUTO_ABILITY_YAML.replace("unit_auto_ability", "unit_fail_ability").replace(
            "name: unit_auto\n", "name: unit_fail\n"
        )
        put = await manifest_store.handle_command(
            "manifest_put_ability",
            {"full_name": "custom.unit_fail", "content": fail_yaml},
            CommandContext.observer("req-m", session_id=None),
        )
        assert put["success"] is True

        unit = engine.get_unit("ability_runner")
        assert isinstance(unit, AbilityRunnerUnit)

        result = await unit.handle_command(
            "execute_ability",
            {
                "agent_name": "agent-a",
                "ability_name": "unit_fail_ability",
                "tool_args": {},
            },
            CommandContext.core(None),
        )
        assert result["success"] is False
        assert result["error"] == "boom"
    finally:
        await engine.stop()


# ── D4: HITL broadcast via event_bus (new path) ─────────────────────────────


async def test_hitl_request_emitted_via_event_bus_on_new_path(tmp_path: Path) -> None:
    """无 legacy callback 时，HITL 请求经 SubjectEventBus 发出（D4 新路径）。"""

    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("ability_runner")
        assert isinstance(unit, AbilityRunnerUnit)

        captured: list[dict[str, Any]] = []

        async def _capture(_event_type: str, payload: Any) -> None:
            captured.append(payload)

        engine.event_bus.subscribe(SUBJECT_HITL_REQUEST_CREATED, _capture)

        # unit_auto_ability 需 HITL（未在 manifest 声明权限，默认 require）
        task = asyncio.create_task(
            unit.handle_command(
                "execute_ability",
                {
                    "agent_name": "agent-hitl",
                    "ability_name": "unit_auto_ability",
                    "tool_args": {},
                },
                CommandContext.core(None),
            )
        )
        # 等待 event_bus 发出 HITL 请求
        for _ in range(100):
            await asyncio.sleep(0.01)
            if captured:
                break

        assert len(captured) == 1
        payload = captured[0]
        assert payload["agent_name"] == "agent-hitl"
        assert payload["ability_name"] == "unit_auto_ability"
        assert "promise_id" in payload
        assert payload["tool_args"] == {}

        # resolve 以释放挂起的 task
        notary = engine.get_unit("hitl_notary")
        assert notary is not None
        notary.service.resolve_promise(
            payload["promise_id"],
            HITLVerdict(approved=False, reason="test"),
        )
        result = await task
        assert result["success"] is False
    finally:
        await engine.stop()


# ── D4: workspace resolution via typed service (new path) ───────────────────


async def test_workspace_resolution_uses_typed_service_on_new_path(
    tmp_path: Path,
) -> None:
    """无 legacy resolver 时，路径解析走 workspace typed service（D4 新路径）。"""

    config = _config(tmp_path)
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="coexistence")

    await engine.start()
    try:
        unit = engine.get_unit("ability_runner")
        assert isinstance(unit, AbilityRunnerUnit)

        # 直接调用内部 _resolve_ws 验证新路径（typed service）
        ws_service = engine.services.require(ABILITY_EXECUTOR)._workspace
        assert ws_service is not None

        # 为 agent-x 创建工作区目录
        from pathlib import Path as PathLib

        ws_dir = PathLib(ws_service.root_path) / "agent-x"
        ws_dir.mkdir(parents=True)

        resolved = unit.service._resolve_ws("agent-x")
        assert resolved == str(ws_dir)

        resolved_missing = unit.service._resolve_ws("no-such-agent")
        assert resolved_missing is None
    finally:
        await engine.stop()
