from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from ghrah.abilities import AbilityRegistry, ActionOutcome, ActionResult
from ghrah.abilities.base import Ability
from ghrah.abilities.context import AbilityExecutionContext
from ouroboros import Context  # type: ignore[import-untyped]
from ouroboros_testutil import wait_active

from ghrah.subject.ability_runner import AbilityRunnerConfig
from ghrah.subject.config import CoreTransportConfig, SubjectConfig
from ghrah.subject.event_bus import SUBJECT_HITL_REQUEST_CREATED
from ghrah.subject.hitl.policy import HITLVerdict
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_unit
from ghrah.subject.runtime.service_keys import ABILITY_EXECUTOR, SANDBOX_EXECUTOR
from ghrah.subject.unit.base import CommandContext, SubjectUnit
from ghrah.subject.units.ability_runner import AbilityRunnerUnit
from ghrah.subject.units.hitl_notary import HITLNotaryUnit
from ghrah.subject.units.hitl_policy import HITLPolicyUnit
from ghrah.subject.units.ledger import LedgerUnit
from ghrah.subject.units.manifest_store import ManifestStoreUnit
from ghrah.subject.units.permissions import PermissionsUnit
from ghrah.subject.units.persistence import PersistenceUnit
from ghrah.subject.units.sandbox import SandboxUnit
from ghrah.subject.units.workspace import WorkspaceUnit

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


def _config(
    tmp_path: Path,
    *,
    core: CoreTransportConfig | None = None,
    ability_runner_slice: AbilityRunnerConfig | None = None,
) -> SubjectConfig:
    kwargs: dict[str, Any] = {
        "workspace_root": str(tmp_path / "workspace"),
        "db_path": str(tmp_path / "subject.db"),
        "manifest_root": str(tmp_path / "manifests"),
    }
    if core is not None:
        kwargs["core"] = core
    if ability_runner_slice is not None:
        kwargs["ability_runner_slice"] = ability_runner_slice
    return SubjectConfig(**kwargs)


_UNIT_TYPES = (
    PersistenceUnit,
    SandboxUnit,
    ManifestStoreUnit,
    LedgerUnit,
    WorkspaceUnit,
    HITLPolicyUnit,
    PermissionsUnit,
    HITLNotaryUnit,
    AbilityRunnerUnit,
)


@asynccontextmanager
async def _boot(
    config: SubjectConfig,
) -> AsyncIterator[tuple[Context, dict[str, SubjectUnit]]]:
    """挂 coexistence 依赖链至 ability_runner，yield (ctx, units)。

    逐个挂载等 ACTIVE（对齐工厂顺序语义，避免多 store 并发开同一 SQLite
    文件触发 database is locked——见阶段 2 实施记录实测新发现 1）。
    """

    async with Context() as ctx:
        units: dict[str, SubjectUnit] = {}
        for unit_type in _UNIT_TYPES:
            unit = unit_type(config)
            units[unit.meta.name] = unit
            fiber = ctx.plugin(mount_unit(unit))
            await wait_active(fiber)
        yield ctx, units


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


# ── Init / borrowing ────────────────────────────────────────────────────────


async def test_ability_runner_unit_init_injects_workspace_event_bus_and_sandbox(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    async with _boot(config) as (ctx, units):
        unit = units["ability_runner"]
        assert isinstance(unit, AbilityRunnerUnit)

        # Service registered under ABILITY_EXECUTOR
        assert ctx.get(ABILITY_EXECUTOR.name) is unit.service

        # D4 新路径注入：workspace typed service + event_bus(ctx 适配) + sandbox_executor
        assert unit.service._workspace is not None
        assert unit.service._event_bus is not None
        assert unit.service._sandbox_executor is ctx.get(SANDBOX_EXECUTOR.name)

        # S2.4：legacy bind_* 回调已移除，不再有 _on_hitl_promise_created/_workspace_resolver
        assert not hasattr(unit.service, "_on_hitl_promise_created")
        assert not hasattr(unit.service, "_workspace_resolver")
        assert not hasattr(unit.service, "bind_hitl_broadcast")
        assert not hasattr(unit.service, "bind_workspace_resolver")


async def test_ability_runner_unit_uses_ability_runner_config_slice(
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        core=CoreTransportConfig(command_timeout=111.0),
        ability_runner_slice=AbilityRunnerConfig(
            hitl_timeout=22.0,
            default_ability_timeout=33.0,
        ),
    )

    async with _boot(config) as (ctx, units):
        unit = units["ability_runner"]
        assert isinstance(unit, AbilityRunnerUnit)

        assert unit.service._config.hitl_timeout == 22.0
        assert unit.service._config.default_ability_timeout == 33.0


# ── handle_command ──────────────────────────────────────────────────────────


async def test_handle_command_unknown_returns_failure(tmp_path: Path) -> None:
    config = _config(tmp_path)

    async with _boot(config) as (_, units):
        unit = units["ability_runner"]
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

    async with _boot(config) as (ctx, units):
        del units
        put = await bridge_command(
            ctx,
            "manifest_put_ability",
            {"full_name": "custom.unit_auto", "content": AUTO_ABILITY_YAML},
        )
        assert put["success"] is True

        result = await bridge_command(
            ctx,
            "execute_ability",
            {
                "request_id": "req-2",
                "agent_name": "agent-a",
                "ability_name": "unit_auto_ability",
                "tool_args": {"k": "v"},
            },
        )
        assert result["success"] is True
        assert result["request_id"] == "req-2"
        assert result["result"] == {"ran": True, "args": {"k": "v"}}
        assert result["error"] is None


async def test_handle_command_failure_ability_returns_error(tmp_path: Path) -> None:
    config = _config(tmp_path)

    async with _boot(config) as (ctx, _):
        fail_yaml = AUTO_ABILITY_YAML.replace("unit_auto_ability", "unit_fail_ability").replace(
            "name: unit_auto\n", "name: unit_fail\n"
        )
        put = await bridge_command(
            ctx,
            "manifest_put_ability",
            {"full_name": "custom.unit_fail", "content": fail_yaml},
        )
        assert put["success"] is True

        result = await bridge_command(
            ctx,
            "execute_ability",
            {
                "agent_name": "agent-a",
                "ability_name": "unit_fail_ability",
                "tool_args": {},
            },
        )
        assert result["success"] is False
        assert result["error"] == "boom"


# ── D4: HITL broadcast via event_bus (new path) ─────────────────────────────


async def test_hitl_request_emitted_via_event_bus_on_new_path(tmp_path: Path) -> None:
    """无 legacy callback 时，HITL 请求经 ctx 事件发出（D4 新路径）。"""

    config = _config(tmp_path)

    async with _boot(config) as (ctx, units):
        captured: list[dict[str, Any]] = []
        ctx.on(
            f"event/{SUBJECT_HITL_REQUEST_CREATED}",
            lambda payload: captured.append(payload),
        )

        # unit_auto_ability 需 HITL（未在 manifest 声明权限，默认 require）
        task = asyncio.create_task(
            bridge_command(
                ctx,
                "execute_ability",
                {
                    "agent_name": "agent-hitl",
                    "ability_name": "unit_auto_ability",
                    "tool_args": {},
                },
            )
        )
        # 等待 ctx 事件发出 HITL 请求
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
        notary = units["hitl_notary"]
        assert isinstance(notary, HITLNotaryUnit)
        notary.service.resolve_promise(
            payload["promise_id"],
            HITLVerdict(approved=False, reason="test"),
        )
        result = await task
        assert result["success"] is False


# ── D4: workspace resolution via typed service (new path) ───────────────────


async def test_workspace_resolution_uses_typed_service_on_new_path(
    tmp_path: Path,
) -> None:
    """无 legacy resolver 时，路径解析走 workspace typed service（D4 新路径）。"""

    config = _config(tmp_path)

    async with _boot(config) as (ctx, units):
        unit = units["ability_runner"]
        assert isinstance(unit, AbilityRunnerUnit)

        # 直接调用内部 _resolve_ws 验证新路径（typed service）
        ws_service = ctx.get(ABILITY_EXECUTOR.name)._workspace
        assert ws_service is not None

        # 为 agent-x 创建工作区目录
        ws_dir = Path(ws_service.root_path) / "agent-x"
        ws_dir.mkdir(parents=True)

        resolved = unit.service._resolve_ws("agent-x")
        assert resolved == str(ws_dir)

        resolved_missing = unit.service._resolve_ws("no-such-agent")
        assert resolved_missing is None
