# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ability 执行器：将 Ability 执行从 Agent 循环中解耦。

核心设计：
- AbilityExecutor 是 Ability 执行的抽象接口
- LocalAbilityExecutor 在 Core 端本地执行 Ability（单体模式）

单体模式下，HITL 在 Core 端处理：
    Hook → HITLFutureStore.create_future() → EventPublisher.publish(HITLRequestEvent)
    → Subject → Observer → 审批 → receive_hitl_response() → resolve_future()
"""

from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ghrah.abilities.context import AbilityExecutionContext
from ghrah.abilities.hook_context import HookContext
from ghrah.abilities.hook_runner import HookRunner
from ghrah.abilities.hook_store import HookStore
from ghrah.abilities.hooks import HookPoint, HookResult
from ghrah.abilities.paths import ABILITY_PATH_SPECS
from ghrah.chat.content import ToolCallBlock
from ghrah.core.ability_protocol import AbilityProtocol
from ghrah.core.event_publisher import EventPublisher
from ghrah.core.events import HITLRequestEvent, HITLResolvedEvent
from ghrah.core.hitl import HITLFutureStore, HITLPromiseRegistry, HITLResult
from ghrah.types.results import ActionOutcome, ActionResult

if TYPE_CHECKING:
    from ghrah.abilities.hooks import Hook
    from ghrah.context.manager import ContextManager

logger = logging.getLogger(__name__)

__all__ = [
    "AbilityExecutor",
    "HitlOutcome",
    "LocalAbilityExecutor",
]

# HITL 审批终态：批准 / 人工拒绝 / 等待超时
HitlOutcome = Literal["approved", "rejected", "timeout"]


class AbilityExecutor(ABC):
    """Ability 执行器接口 — 将执行与 Agent 循环解耦。

    默认实现为 LocalAbilityExecutor（在 Core 端直接执行 Ability + HITL）。

    子类必须实现：
    - execute_ability(): 执行单个 Ability
    - execute_tool_calls(): 执行一组 tool_calls
    - handle_hitl_hook_result(): 处理 HITL Hook 结果
    - update_hooks(): 同步 Hook 列表
    - update_event_publisher(): 同步事件发布器
    - receive_hitl_response(): 接收 HITL 审批结果
    """

    @abstractmethod
    async def execute_ability(
        self,
        ability: AbilityProtocol,
        context: AbilityExecutionContext,
    ) -> ActionResult:
        """执行单个 Ability。

        Args:
            ability: 要执行的 Ability 实例
            context: 执行上下文

        Returns:
            执行结果
        """
        ...

    @abstractmethod
    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCallBlock],
        abilities: dict[str, AbilityProtocol],
        accumulated_data: dict[str, Any],
        context_manager: ContextManager,
        last_action_result: ActionResult | None = None,
    ) -> list[dict]:
        """执行一组 tool_calls，返回结果列表。

        每个 tool_call 映射到对应的 Ability 执行。

        Args:
            tool_calls: LLM 返回的 ToolCallBlock 列表
            abilities: 已注册的 Ability 字典
            accumulated_data: 累积数据
            context_manager: 上下文管理器
            last_action_result: 上一次 action 的结果（由 ActorAgent 从 IterationState 显式传入）

        Returns:
            结果列表，每个 dict 包含 "ability_name", "action_result", "tool_call_id"
        """
        ...

    @abstractmethod
    async def handle_hitl_hook_result(
        self,
        hook_result: HookResult,
        context: AbilityExecutionContext,
    ) -> HitlOutcome:
        """处理 HITL Hook 结果。

        当 PRE_EXECUTE Hook 返回 should_continue=False 且 requires_hitl=True 时，
        执行器需要决定如何处理：单体模式创建 Future 等待审批，分布式模式委托给 Subject。

        Args:
            hook_result: Hook 返回的结果
            context: 当前执行上下文

        Returns:
            审批终态："approved"（继续执行）/ "rejected"（人工拒绝）/ "timeout"（等待超时）
        """
        ...

    @abstractmethod
    def update_hooks(self, hooks: list[Hook]) -> None:
        """同步更新 Hook 列表。

        当 Agent 注册/反注册 Ability 时，需要同步更新执行器的 Hook 列表。

        Args:
            hooks: 最新的 Hook 列表
        """
        ...

    @abstractmethod
    def update_event_publisher(self, publisher: EventPublisher) -> None:
        """同步更新事件发布器。

        当 Agent 的事件发布器变更时，需要同步更新执行器的事件发布器。

        Args:
            publisher: 新的事件发布器
        """
        ...

    @abstractmethod
    def receive_hitl_response(
        self,
        ability_name: str,
        tool_call_id: str,
        approved: bool,
        result: Any = None,
    ) -> bool:
        """接收 HITL 审批结果。

        当 Observer 审批 HITL 请求后，通过此方法 resolve 对应的 Future。
        由 LocalAbilityExecutor 处理。

        Args:
            ability_name: Ability 名称
            tool_call_id: 工具调用 ID
            approved: 是否批准
            result: 审批附加结果

        Returns:
            是否成功解析 Future
        """
        ...


class LocalAbilityExecutor(AbilityExecutor):
    """本地执行器 — 在 Core 端直接执行 Ability。

    保留当前所有行为：
    - PRE_EXECUTE / POST_EXECUTE Hook
    - HITL 审批（通过 HITLFutureStore）
    - 本地 I/O 操作

    用于单体模式（ghrah-core 独立使用）。
    """

    def __init__(
        self,
        agent_name: str,
        hooks: list[Hook] | None = None,
        hook_runner: HookRunner | None = None,
        event_publisher: EventPublisher | None = None,
        hitl_timeout: float = 300.0,
        workspace_root: str | None = None,
        hitl_promise_registry: HITLPromiseRegistry | None = None,
    ) -> None:
        """初始化本地执行器。

        Args:
            agent_name: Agent 名称（用于 HITL Future 的 key）
            hooks: 已注册的 Hook 列表
            hook_runner: 可选共享 HookRunner（由 ActorAgent 注入）
            event_publisher: 事件发布器（默认 NullEventPublisher）
            hitl_timeout: HITL 等待超时时间（秒）
            workspace_root: 工作区根目录，用于将相对路径解析到沙盒内（None 表示不解析）
            hitl_promise_registry: HITL promise 注册表（CoreUnit 注入，unit 命令面
                按 promise_id 翻译回三元组；None 时 standalone 模式跳过注册）
        """
        self._agent_name = agent_name
        self._hook_store = HookStore()
        if hooks:
            self._hook_store.add_hooks(HookStore.AGENT_OWNER, hooks)
        self._hook_runner = hook_runner or HookRunner(self._hook_store)
        if event_publisher is not None:
            self._event_publisher: EventPublisher = event_publisher
        else:
            from ghrah.core.event_publisher import NullEventPublisher

            self._event_publisher = NullEventPublisher()
        self._hitl_store = HITLFutureStore()
        self._hitl_timeout = hitl_timeout
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._hitl_promise_registry = hitl_promise_registry

    @property
    def hitl_store(self) -> HITLFutureStore:
        """获取 HITL Future 存储（供外部 resolve 使用）。"""
        return self._hitl_store

    @property
    def hitl_promise_registry(self) -> HITLPromiseRegistry | None:
        """获取 HITL promise 注册表（无注入时为 None，standalone 兼容）。"""
        return self._hitl_promise_registry

    def update_hitl_promise_registry(self, registry: HITLPromiseRegistry) -> None:
        """同步更新 HITL promise 注册表（CoreUnit spawn 后 best-effort 注入）。"""
        self._hitl_promise_registry = registry

    def update_hooks(self, hooks: list[Hook]) -> None:
        """兼容旧接口：替换本地私有 HookStore 中的 hooks。

        Args:
            hooks: 最新的 Hook 列表
        """
        self._hook_store.remove_owner(HookStore.AGENT_OWNER)
        self._hook_store.add_hooks(HookStore.AGENT_OWNER, hooks)

    def update_hook_runner(self, hook_runner: HookRunner) -> None:
        """Use the agent-level HookRunner after ActorAgent wires shared storage."""

        self._hook_runner = hook_runner

    def update_event_publisher(self, publisher: EventPublisher) -> None:
        """同步更新事件发布器。

        Args:
            publisher: 新的事件发布器
        """
        self._event_publisher = publisher

    async def execute_ability(
        self,
        ability: AbilityProtocol,
        context: AbilityExecutionContext,
    ) -> ActionResult:
        """执行单个 Ability，包含 PRE_EXECUTE 和 POST_EXECUTE Hook。

        如果 PRE_EXECUTE Hook 返回 should_continue=False 且包含 HITL 请求，
        会创建 Future 等待审批结果。

        Args:
            ability: 要执行的 Ability 实例
            context: 执行上下文

        Returns:
            执行结果

        Raises:
            HookError: Hook 执行出错时
        """
        # PRE_EXECUTE hook（ability 级）
        hook_result = await self._hook_runner.run(
            HookContext.from_ability_context(HookPoint.PRE_EXECUTE, context)
        )

        # 处理 Hook 结果
        if hook_result is not None:
            if not hook_result.should_continue:
                if hook_result.requires_hitl:
                    # 需要 HITL 审批：创建 Future 等待人工审批
                    hitl_outcome = await self.handle_hitl_hook_result(hook_result, context)
                    if hitl_outcome != "approved":
                        # 人工拒绝或等待超时——错误信息区分两者，超时不得
                        # 折算成"用户拒绝"信号进 LLM 上下文
                        if hitl_outcome == "timeout":
                            return ActionResult(
                                outcome=ActionOutcome.FAILURE,
                                data={
                                    "error": (
                                        f"HITL approval timed out after {self._hitl_timeout}s "
                                        f"with no response delivered; "
                                        f"ability={context.current_ability_name}"
                                    ),
                                    "hitl_timeout": True,
                                },
                            )
                        return ActionResult(
                            outcome=ActionOutcome.FAILURE,
                            data={
                                "error": hook_result.message or "Execution blocked by HITL",
                                "hitl_rejected": True,
                            },
                        )
                    # HITL 批准，继续执行
                else:
                    # 直接拦截，不进入 HITL 等待流程
                    return ActionResult(
                        outcome=ActionOutcome.FAILURE,
                        data={
                            "error": hook_result.message or "Execution blocked by hook",
                        },
                    )
            elif hook_result.route_to:
                # 路由到其他 ability
                return ActionResult(
                    outcome=ActionOutcome.DELEGATE,
                    data={"route_to": hook_result.route_to},
                    next_action_hint=hook_result.route_to,
                )
            elif hook_result.modified_context:
                # 合并修改的上下文
                context.accumulated_data.update(hook_result.modified_context)

        # 执行 Ability
        action_result = await ability.execute(context)

        # POST_EXECUTE hook（ability 级）
        await self._hook_runner.run(
            HookContext.from_ability_context(HookPoint.POST_EXECUTE, context, action_result)
        )

        return action_result

    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCallBlock],
        abilities: dict[str, AbilityProtocol],
        accumulated_data: dict[str, Any],
        context_manager: ContextManager,
        last_action_result: ActionResult | None = None,
    ) -> list[dict]:
        """执行一组 tool_calls，返回结果列表。

        多个 tool_calls 使用 asyncio.gather 并行执行。

        Args:
            tool_calls: LLM 返回的 ToolCallBlock 列表
            abilities: 已注册的 Ability 字典
            accumulated_data: 累积数据
            context_manager: 上下文管理器
            last_action_result: 上一次 action 的结果（由 ActorAgent 从 IterationState 显式传入）

        Returns:
            结果列表，每个 dict 包含 "ability_name", "action_result", "tool_call_id"
        """
        results: list[dict] = []
        tool_call_tasks: list[tuple[AbilityProtocol, dict[str, Any], str]] = []
        task_ability_names: list[str] = []

        for tc in tool_calls:
            ability_name = tc.name
            ability_args = tc.arguments
            tool_call_id = tc.id

            ability = abilities.get(ability_name)
            if ability is None:
                # 未知 ability，直接记录失败结果
                results.append(
                    {
                        "ability_name": ability_name,
                        "action_result": ActionResult(
                            outcome=ActionOutcome.FAILURE,
                            data={"error": f"Unknown ability: {ability_name}"},
                        ),
                        "tool_call_id": tool_call_id,
                    }
                )
                continue

            tool_call_tasks.append((ability, ability_args, tool_call_id))
            task_ability_names.append(ability_name)

        if tool_call_tasks:
            # 为每个 ability 创建独立的 AbilityExecutionContext
            raw_results = await asyncio.gather(
                *[
                    self._execute_single_with_context(
                        ability,
                        args,
                        accumulated_data,
                        context_manager,
                        last_action_result,
                    )
                    for ability, args, _tc_id in tool_call_tasks
                ],
                return_exceptions=True,
            )
            for i, r in enumerate(raw_results):
                if isinstance(r, Exception):
                    results.append(
                        {
                            "ability_name": task_ability_names[i],
                            "action_result": ActionResult(
                                outcome=ActionOutcome.FAILURE,
                                data={"error": str(r)},
                            ),
                            "tool_call_id": tool_call_tasks[i][2],
                        }
                    )
                else:
                    r["tool_call_id"] = tool_call_tasks[i][2]
                    results.append(r)

        return results

    async def _execute_single_with_context(
        self,
        ability: AbilityProtocol,
        tool_args: dict[str, Any],
        accumulated_data: dict[str, Any],
        context_manager: ContextManager,
        last_action_result: ActionResult | None = None,
    ) -> dict:
        """执行单个 ability（用于并行执行），创建独立的 AbilityExecutionContext。

        Args:
            ability: 要执行的 ability 实例
            tool_args: 工具调用参数
            accumulated_data: 累积数据
            context_manager: 上下文管理器
            last_action_result: 上一次 action 的结果（由 ActorAgent 从 IterationState 显式传入）

        Returns:
            dict 包含 "ability_name" 和 "action_result"
        """
        resolved_args = self._resolve_paths(tool_args, ability.name)

        per_ability_context = AbilityExecutionContext(
            current_ability_name=ability.name,
            tool_args=resolved_args,
            agent_state=context_manager.get_current_state(),
            context_manager=context_manager,
            accumulated_data={
                **copy.deepcopy(accumulated_data),
                "tool_args": resolved_args,
            },
            last_action_result=last_action_result,
            agent_name=self._agent_name,
        )

        action_result = await self.execute_ability(ability, per_ability_context)

        return {"ability_name": ability.name, "action_result": action_result}

    def _resolve_paths(self, tool_args: dict[str, Any], ability_name: str) -> dict[str, Any]:
        """将 tool_args 中的相对路径解析到 workspace_root 下。

        如果 workspace_root 未设置，直接返回原 tool_args。
        仅对 ABILITY_PATH_SPECS 中已知的路径参数进行解析，
        绝对路径保持不变。

        Args:
            tool_args: LLM 工具调用参数
            ability_name: Ability 名称

        Returns:
            解析后的 tool_args（副本）
        """
        if self._workspace_root is None:
            return tool_args

        spec = ABILITY_PATH_SPECS.get(ability_name)
        if spec is None:
            return tool_args

        resolved = dict(tool_args)
        for key in spec.path_keys:
            value = resolved.get(key)
            if value and isinstance(value, str) and not Path(value).is_absolute():
                resolved[key] = str((Path(self._workspace_root) / value).resolve())
        for key in spec.working_dir_keys:
            value = resolved.get(key)
            if value and isinstance(value, str) and not Path(value).is_absolute():
                resolved[key] = str((Path(self._workspace_root) / value).resolve())

        return resolved

    async def handle_hitl_hook_result(
        self,
        hook_result: HookResult,
        context: AbilityExecutionContext,
    ) -> HitlOutcome:
        """处理 HITL Hook 结果。

        在单体模式下，创建 asyncio.Future 等待 HITL 审批：
        1. 生成 promise_id，发布 HITLRequestEvent（携带 promise_id）到 EventPublisher
        2. 创建 HITL Future（promise 登记到注册表）并等待
        3. 收到审批结果后继续或终止

        Args:
            hook_result: Hook 返回的结果
            context: 当前执行上下文

        Returns:
            审批终态："approved" / "rejected" / "timeout"
        """
        # 生成 tool_call_id 与 promise_id
        tool_call_id = context.tool_args.get("call_id", "") or uuid.uuid4().hex[:12]
        promise_id = uuid.uuid4().hex

        # 发布 HITL 请求事件（promise_id 随载荷下发，Observer 凭此回发审批）
        await self._event_publisher.publish(
            HITLRequestEvent(
                agent_name=self._agent_name,
                ability_name=context.current_ability_name,
                tool_call=context.tool_args,
                context={"tool_call_id": tool_call_id},
                promise_id=promise_id,
            )
        )

        # 创建 Future 并等待
        future = self._hitl_store.create_future(
            agent_name=self._agent_name,
            ability_name=context.current_ability_name,
            tool_call_id=tool_call_id,
        )
        if self._hitl_promise_registry is not None:
            self._hitl_promise_registry.register(
                promise_id=promise_id,
                agent_name=self._agent_name,
                ability_name=context.current_ability_name,
                tool_call_id=tool_call_id,
            )

        # 等待 HITL 结果（带超时）
        try:
            hitl_result: HITLResult = await asyncio.wait_for(future, timeout=self._hitl_timeout)
            outcome: HitlOutcome = "approved" if hitl_result.approved else "rejected"
            if self._hitl_promise_registry is not None:
                self._hitl_promise_registry.remove(promise_id)
            logger.info(
                f"LocalAbilityExecutor[{self._agent_name}] HITL {outcome}: "
                f"ability={context.current_ability_name}, tool_call_id={tool_call_id}"
            )
            await self._event_publisher.publish(
                HITLResolvedEvent(
                    agent_name=self._agent_name,
                    promise_id=promise_id,
                    ability_name=context.current_ability_name,
                    tool_call_id=tool_call_id,
                    status=outcome,
                )
            )
            return outcome
        except TimeoutError:
            logger.warning(
                f"LocalAbilityExecutor[{self._agent_name}] HITL request timed out: "
                f"ability={context.current_ability_name}, tool_call_id={tool_call_id}"
            )
            if self._hitl_promise_registry is not None:
                self._hitl_promise_registry.remove_triplet(
                    agent_name=self._agent_name,
                    ability_name=context.current_ability_name,
                    tool_call_id=tool_call_id,
                )
            await self._event_publisher.publish(
                HITLResolvedEvent(
                    agent_name=self._agent_name,
                    promise_id=promise_id,
                    ability_name=context.current_ability_name,
                    tool_call_id=tool_call_id,
                    status="timeout",
                )
            )
            return "timeout"

    def receive_hitl_response(
        self,
        ability_name: str,
        tool_call_id: str,
        approved: bool,
        result: Any = None,
    ) -> bool:
        """接收 HITL 审批结果（由外部调用）。

        当 Observer 审批 HITL 请求后，通过此方法 resolve 对应的 Future。

        Args:
            ability_name: Ability 名称
            tool_call_id: 工具调用 ID
            approved: 是否批准
            result: 审批附加结果

        Returns:
            是否成功解析 Future
        """
        hitl_result = HITLResult(approved=approved, result=result)
        resolved = self._hitl_store.resolve_future(
            agent_name=self._agent_name,
            ability_name=ability_name,
            tool_call_id=tool_call_id,
            result=hitl_result,
        )
        if resolved:
            logger.info(
                f"LocalAbilityExecutor[{self._agent_name}] HITL response received: "
                f"ability={ability_name}, tool_call_id={tool_call_id}, approved={approved}"
            )
        else:
            logger.warning(
                f"LocalAbilityExecutor[{self._agent_name}] HITL response ignored "
                f"(no pending future): ability={ability_name}, tool_call_id={tool_call_id}"
            )
        return resolved
