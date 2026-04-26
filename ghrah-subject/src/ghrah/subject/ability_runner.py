"""Subject 端 Ability 执行器。

接收 Core（通过 Gateway）的 EXECUTE_ABILITY 命令，
在本地执行 Ability，执行前通过 HITLNotary 检查权限。

执行流程：
1. 从 AbilityRegistry 查找 Ability 类并实例化
2. 通过 PermissionChecker 检查硬性权限（拒绝 vs 需要 HITL vs 允许）
3. 通过 HITLNotary 检查策略级权限（是否需要人工审批）
4. 如需 HITL：创建 Promise，广播请求，等待审批后继续或终止
5. 本地执行 Ability
6. 返回 ActionResult
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from ghrah.abilities import (
    AbilityExecutionContext,
    AbilityRegistry,
    ActionOutcome,
    ActionResult,
)
from ghrah.subject.hitl.notary import HITLNotary
from ghrah.subject.hitl.policy import HITLVerdict
from ghrah.subject.permission_checker import PermissionChecker, PermissionDecision

logger = logging.getLogger(__name__)

__all__ = ["AbilityRunner", "AbilityRunnerConfig"]


@dataclass
class AbilityRunnerConfig:
    """AbilityRunner 配置。

    Attributes:
        hitl_timeout: HITL 审批超时时间（秒），None 表示无限等待
        default_ability_timeout: Ability 执行超时时间（秒）
    """

    hitl_timeout: float | None = None
    default_ability_timeout: float = 300.0


class AbilityRunner:
    """Subject 端 Ability 执行器。

    接收 Core 的 EXECUTE_ABILITY 命令，在本地执行 Ability。
    执行前通过 HITLNotary 检查是否需要人工审批。

    分布式模式下：
    1. Core 通过 Gateway 发送 execute_ability 请求
    2. Subject AbilityRunner 接收请求
    3. 权限检查（PermissionChecker 硬性拒绝 + HITLNotary 审批）
    4. 本地执行 Ability（Subject 持有工作区和物理状态）
    5. 将 ActionResult 通过 Gateway 返回给 Core
    """

    def __init__(
        self,
        hitl_notary: HITLNotary,
        permission_checker: PermissionChecker | None = None,
        config: AbilityRunnerConfig | None = None,
    ) -> None:
        self._hitl_notary = hitl_notary
        self._permission_checker = permission_checker or PermissionChecker()
        self._config = config or AbilityRunnerConfig()

    async def execute_ability(
        self,
        ability_name: str,
        tool_args: dict[str, Any],
        agent_name: str,
        agent_state: dict[str, Any] | None = None,
    ) -> ActionResult:
        """执行 Ability 的完整流程。

        Args:
            ability_name: Ability 名称（在 AbilityRegistry 中注册的类型名）
            tool_args: 工具调用参数（从 LLM tool call 解析）
            agent_name: 请求的 Agent 名称
            agent_state: Agent 状态（可选，用于构建执行上下文）

        Returns:
            ActionResult: 执行结果
        """
        ability_cls = AbilityRegistry.get_class(ability_name)
        if ability_cls is None:
            logger.error("Ability not found: %s", ability_name)
            return ActionResult(
                outcome=ActionOutcome.FAILURE,
                data={"error": f"Ability not found: {ability_name}"},
            )

        perm_verdict = self._permission_checker.check_ability(ability_name, tool_args)
        if perm_verdict.decision == PermissionDecision.DENY:
            logger.warning(
                "Permission denied for ability=%s: %s",
                ability_name,
                perm_verdict.reason,
            )
            return ActionResult(
                outcome=ActionOutcome.FAILURE,
                data={
                    "error": perm_verdict.reason,
                    "ability_name": ability_name,
                },
            )

        # HITL 需要判断：PermissionChecker 路径级 HITL 或 HITLPolicy 能力级 HITL
        # 路径级 HITL（REQUIRE_HITL 含路径元数据）不可被 HITLPolicy 覆盖
        is_path_hitl = (
            perm_verdict.decision == PermissionDecision.REQUIRE_HITL
            and "path" in perm_verdict.metadata
        )
        hitl_verdict = self._hitl_notary.check_request(agent_name, ability_name, tool_args)

        if is_path_hitl:
            needs_hitl = True
        else:
            needs_hitl = not hitl_verdict.approved

        if needs_hitl:
            verdict = await self._await_hitl_approval(agent_name, ability_name, tool_args)
            if not verdict.approved:
                logger.info(
                    "HITL rejected: agent=%s ability=%s reason=%s",
                    agent_name,
                    ability_name,
                    verdict.reason,
                )
                return ActionResult(
                    outcome=ActionOutcome.FAILURE,
                    data={
                        "error": f"HITL rejected: {verdict.reason}",
                        "ability_name": ability_name,
                    },
                )

        try:
            ability = ability_cls()
            context = AbilityExecutionContext(
                current_ability_name=ability_name,
                tool_args=tool_args,
                agent_state=agent_state or {},
            )
            result = await asyncio.wait_for(
                ability.execute(context),
                timeout=self._config.default_ability_timeout,
            )
            logger.info(
                "Ability executed: ability=%s outcome=%s agent=%s",
                ability_name,
                result.outcome.value,
                agent_name,
            )
            return result
        except TimeoutError:
            logger.error(
                "Ability execution timed out: ability=%s timeout=%.1f",
                ability_name,
                self._config.default_ability_timeout,
            )
            return ActionResult(
                outcome=ActionOutcome.FAILURE,
                data={
                    "error": f"Ability execution timed out: {ability_name}",
                    "ability_name": ability_name,
                },
            )
        except Exception as e:
            logger.error(
                "Ability execution failed: ability=%s error=%s",
                ability_name,
                e,
                exc_info=True,
            )
            return ActionResult(
                outcome=ActionOutcome.FAILURE,
                data={
                    "error": str(e),
                    "ability_name": ability_name,
                },
            )

    async def execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        agent_name: str,
        agent_state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """并行执行多个 tool_calls。

        Args:
            tool_calls: LLM 返回的 tool_calls 列表
            agent_name: 请求的 Agent 名称
            agent_state: Agent 状态

        Returns:
            结果列表，每个 dict 包含 "ability_name", "action_result", "tool_call_id"
        """
        results: list[dict[str, Any]] = []
        tasks: list[tuple[str, dict[str, Any], str]] = []

        for tc in tool_calls:
            ability_name = tc.get("name", tc.get("function", {}).get("name", ""))
            ability_args = tc.get("args", tc.get("arguments", {}))
            tool_call_id = tc.get("id", "")

            if isinstance(ability_args, str):
                try:
                    ability_args = json.loads(ability_args)
                except (json.JSONDecodeError, TypeError):
                    ability_args = {}

            tasks.append((ability_name, ability_args, tool_call_id))

        if tasks:
            raw_results = await asyncio.gather(
                *[
                    self._execute_single(ability_name, ability_args, agent_name, agent_state)
                    for ability_name, ability_args, _ in tasks
                ],
                return_exceptions=True,
            )
            for i, r in enumerate(raw_results):
                if isinstance(r, Exception):
                    results.append(
                        {
                            "ability_name": tasks[i][0],
                            "action_result": ActionResult(
                                outcome=ActionOutcome.FAILURE,
                                data={"error": str(r)},
                            ),
                            "tool_call_id": tasks[i][2],
                        }
                    )
                else:
                    results.append(
                        {
                            "ability_name": tasks[i][0],
                            "action_result": r,
                            "tool_call_id": tasks[i][2],
                        }
                    )

        return results

    async def _execute_single(
        self,
        ability_name: str,
        tool_args: dict[str, Any],
        agent_name: str,
        agent_state: dict[str, Any] | None = None,
    ) -> ActionResult:
        """执行单个 Ability，将所有异常转换为 FAILURE ActionResult。"""
        try:
            return await self.execute_ability(ability_name, tool_args, agent_name, agent_state)
        except Exception as e:
            return ActionResult(
                outcome=ActionOutcome.FAILURE,
                data={"error": str(e), "ability_name": ability_name},
            )

    async def _await_hitl_approval(
        self,
        agent_name: str,
        ability_name: str,
        tool_args: dict[str, Any],
    ) -> HITLVerdict:
        """创建 HITL Promise 并等待审批结果。

        如果配置了超时，等待超时后自动拒绝。
        """
        promise = self._hitl_notary.create_promise(agent_name, ability_name, tool_args)
        logger.info(
            "HITL promise created: id=%s agent=%s ability=%s, waiting for approval",
            promise.promise_id,
            agent_name,
            ability_name,
        )

        try:
            if self._config.hitl_timeout is not None:
                verdict = await asyncio.wait_for(
                    promise.future,
                    timeout=self._config.hitl_timeout,
                )
            else:
                verdict = await promise.future
        except TimeoutError:
            logger.warning(
                "HITL promise timed out: id=%s agent=%s ability=%s",
                promise.promise_id,
                agent_name,
                ability_name,
            )
            self._hitl_notary.cancel_promise(promise.promise_id)
            return HITLVerdict(approved=False, reason="hitl_timeout")
        except asyncio.CancelledError:
            logger.warning(
                "HITL promise cancelled: id=%s agent=%s ability=%s",
                promise.promise_id,
                agent_name,
                ability_name,
            )
            return HITLVerdict(approved=False, reason="hitl_cancelled")

        return verdict
