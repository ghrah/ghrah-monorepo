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
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ghrah.abilities import (
    AbilityExecutionContext,
    AbilityRegistry,
    ActionOutcome,
    ActionResult,
)
from ghrah.subject.hitl.notary import HITLNotary, HITLPromise
from ghrah.subject.hitl.policy import HITLVerdict
from ghrah.subject.permission_checker import PermissionChecker, PermissionDecision

if TYPE_CHECKING:
    from ghrah.subject.sandbox.executor import SandboxExecutor

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
    3. 路径解析：将相对路径解析为 Agent 工作区内的绝对路径
    4. 权限检查（PermissionChecker 硬性拒绝 + HITLNotary 审批）
    5. 本地执行 Ability（Subject 持有工作区和物理状态）
    6. 将 ActionResult 通过 Gateway 返回给 Core
    """

    # 需要路径解析的 Ability 和对应的路径参数名
    PATH_ABILITIES: dict[str, list[str]] = {
        "read_file": ["file_path"],
        "write_file": ["file_path"],
        "edit_file": ["file_path"],
        "delete_file": ["file_path"],
        "list_directory": ["dir_path"],
        "move_file": ["source_path", "destination_path"],
    }

    # 需要工作目录路径解析的 Ability（working_dir 参数需要相对→绝对路径转换）
    WORKING_DIR_ABILITIES: dict[str, list[str]] = {
        "execute_command": ["working_dir"],
    }

    def __init__(
        self,
        hitl_notary: HITLNotary,
        permission_checker: PermissionChecker | None = None,
        config: AbilityRunnerConfig | None = None,
        sandbox_executor: SandboxExecutor | None = None,
    ) -> None:
        self._hitl_notary = hitl_notary
        self._permission_checker = permission_checker or PermissionChecker()
        self._config = config or AbilityRunnerConfig()
        self._sandbox_executor = sandbox_executor
        self._on_hitl_promise_created: Callable[[HITLPromise], Awaitable[None]] | None = None
        # 工作区路径解析器：agent_name → workspace 绝对路径
        self._workspace_resolver: Callable[[str], str | None] | None = None

    def bind_hitl_broadcast(self, callback: Callable[[HITLPromise], Awaitable[None]]) -> None:
        """绑定 HITL Promise 创建回调。

        当 AbilityRunner 创建 HITL Promise 时，调用此回调将请求广播给 Observer。
        分布式模式下由 SubjectService 调用此方法注入 Gateway 广播逻辑。

        Args:
            callback: 接收 HITLPromise 的异步回调，用于将 HITL 请求发送给 Observer。
        """
        self._on_hitl_promise_created = callback

    def bind_workspace_resolver(self, resolver: Callable[[str], str | None]) -> None:
        """绑定工作区路径解析器。

        当 AbilityRunner 执行 Ability 时，调用此解析器将 agent_name 映射到
        工作区绝对路径，用于将 Agent 提供的相对路径解析为工作区内绝对路径。

        分布式模式下由 SubjectService 调用此方法注入 WorkspaceManager 路径查询。

        Args:
            resolver: 接收 agent_name，返回工作区绝对路径（str）或 None。
        """
        self._workspace_resolver = resolver

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
            tool_args: 工具调用参数（从 tool call 解析）
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

        # 路径解析：将 Agent 提供的相对路径解析为 Agent 工作区内的绝对路径
        tool_args = self._resolve_paths(ability_name, tool_args, agent_name)

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
            if ability_name == "execute_command" and self._sandbox_executor is not None:
                ability = ability_cls(command_runner=self._sandbox_executor)
            else:
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
            tool_calls: tool_calls 列表
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

    def _resolve_paths(
        self,
        ability_name: str,
        tool_args: dict[str, Any],
        agent_name: str,
    ) -> dict[str, Any]:
        """将 tool_args 中的相对路径解析为 Agent 工作区内的绝对路径。

        Agent 提供的路径（如 "hello.py"）是相对于 Agent 工作区的，
        但 PermissionChecker 和 Ability 的 execute() 方法需要绝对路径。
        此方法将相对路径拼接为 workspace_root/agent_name/relative_path。

        如果工作区解析器未绑定或 Agent 无工作区，则不修改路径。
        绝对路径（以 / 开头）不修改。

        Args:
            ability_name: Ability 名称
            tool_args: 工具调用参数
            agent_name: Agent 名称

        Returns:
            路径解析后的 tool_args（浅拷贝）
        """
        path_keys = self.PATH_ABILITIES.get(ability_name)
        working_dir_keys = self.WORKING_DIR_ABILITIES.get(ability_name)

        if path_keys is None and working_dir_keys is None:
            return tool_args

        workspace_path = (
            self._workspace_resolver(agent_name) if self._workspace_resolver else None
        )
        if not workspace_path:
            logger.debug(
                "No workspace for agent=%s, using raw paths for ability=%s",
                agent_name, ability_name,
            )
            return tool_args

        resolved = dict(tool_args)

        if path_keys:
            for key in path_keys:
                value = resolved.get(key)
                if not value or not isinstance(value, str):
                    continue
                if os.path.isabs(value):
                    continue
                resolved[key] = os.path.join(workspace_path, value)
                logger.info(
                    "Resolved path for agent=%s ability=%s: %s → %s",
                    agent_name, ability_name, value, resolved[key],
                )

        if working_dir_keys:
            for key in working_dir_keys:
                value = resolved.get(key)
                if not value or not isinstance(value, str):
                    continue
                if os.path.isabs(value):
                    continue
                resolved[key] = os.path.join(workspace_path, value)
                logger.info(
                    "Resolved working_dir for agent=%s ability=%s: %s → %s",
                    agent_name, ability_name, value, resolved[key],
                )

        return resolved

    async def _await_hitl_approval(
        self,
        agent_name: str,
        ability_name: str,
        tool_args: dict[str, Any],
    ) -> HITLVerdict:
        """创建 HITL Promise 并等待审批结果。

        如果配置了超时，等待超时后自动拒绝。
        创建 Promise 后调用绑定回调（如 SubjectService 的 Gateway 广播），
        将 HITL 请求发送给 Observer。
        """
        promise = self._hitl_notary.create_promise(agent_name, ability_name, tool_args)
        logger.info(
            "HITL promise created: id=%s agent=%s ability=%s, waiting for approval",
            promise.promise_id,
            agent_name,
            ability_name,
        )

        if self._on_hitl_promise_created is not None:
            await self._on_hitl_promise_created(promise)

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
