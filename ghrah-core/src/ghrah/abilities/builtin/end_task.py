# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EndTaskAbility：终止循环并生成最终回复。

这个 Ability 用于：
- 显式终止 Agent 的执行循环
- 作为 Hook 路由的目标（如 MaxIterationHook 强制路由到 end_task）
- 收集累积数据，生成摘要

执行逻辑：
1. 从 AbilityExecutionContext.accumulated_data 中收集数据
2. 如果有 last_action_result，直接使用其内容作为最终回复
3. 返回 ActionResult(outcome=SUCCESS)，Agent 的 _build_response 会提取回复

- mode 参数支持三种模式：auto / toolcall / verified
- bind_tool() 方法在 mode="toolcall" 时返回 function calling schema
- 当前最简版本只支持 mode="auto"（被 Hook 触发）

内置 Hook：
    EndTaskDoneHook：AFTER_ACTION 触发，执行后终止驱动循环。
    toolcall 模式下 LLM 主动调用 end_task 后，返回值本身不控制循环
    （驱动循环只消费 Hook 的 should_continue），必须由该 Hook 终止；
    Hook 路由路径（_execute_routed_ability）不经 AFTER_ACTION，故不受影响。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ghrah.abilities.base import Ability
from ghrah.abilities.hooks import Hook, HookPoint, HookResult
from ghrah.types.results import ActionOutcome, ActionResult

if TYPE_CHECKING:
    from ghrah.abilities.context import AbilityExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["EndTaskAbility", "EndTaskDoneHook"]


class EndTaskDoneHook(Hook):
    """EndTaskAbility 执行完成后终止驱动循环。

    与 ConversationDoneHook 对称：驱动循环只依据 Hook 的 should_continue
    决定是否继续，Ability 返回的 next_action_hint 不被消费，因此 toolcall
    模式的 end_task 需要一个 AFTER_ACTION Hook 来显式终止。
    """

    hook_point = HookPoint.AFTER_ACTION

    async def should_trigger(self, context: AbilityExecutionContext) -> bool:
        """只在当前 ability 是 end_task 时触发。"""
        return context.current_ability_name == "end_task"

    async def execute(
        self, context: AbilityExecutionContext, result: ActionResult | None
    ) -> HookResult:
        """终止循环。"""
        return HookResult.stop()


class EndTaskAbility(Ability):
    """终止任务能力 — 停止执行循环并生成最终回复。


    - mode: 支持三种模式（auto / toolcall / verified）
      - auto: 被 Hook 触发（默认，当前唯一实现的模式）
      - toolcall: 通过 function call 触发
      - verified: 需要验证器确认后终止
    - bind_tool(): 当 mode="toolcall" 时返回 end_task 的 function calling schema

    特点：
    - execute() 从上下文中收集数据生成最终回复
    - next_action_hint 为 None（明确表示任务结束）

    用法::

        end_task = EndTaskAbility()
        agent.register_ability(end_task)

        # 通过 Hook 强制路由
        MaxIterationHook → route_to="end_task"
    """

    def __init__(
        self,
        hooks: list[Hook] | None = None,
        mode: str = "auto",
    ) -> None:
        if mode not in ("auto", "toolcall", "verified"):
            raise ValueError(f"Invalid mode: {mode!r}, expected 'auto', 'toolcall', or 'verified'")
        self._hooks: list[Hook] = [EndTaskDoneHook()]
        if hooks:
            self._hooks.extend(hooks)
        self._mode = mode

    @property
    def name(self) -> str:
        return "end_task"

    @property
    def mode(self) -> str:
        """当前终止模式。"""
        return self._mode

    def bind_tool(self) -> dict[str, Any] | None:
        """当 mode == 'toolcall' 时返回 end_task 的 function calling schema。"""
        if self._mode == "toolcall":
            # TODO: Phase 1 - 返回 end_task 的 function calling schema
            return {
                "type": "function",
                "function": {
                    "name": "end_task",
                    "description": "End the current task and generate a final response",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "Optional summary of the task result",
                            },
                        },
                        "required": [],
                    },
                },
            }
        return None

    def to_prompt_description(self) -> str:
        return "End the current task and generate a final response"

    def get_hooks(self) -> list[Hook]:
        return list(self._hooks)

    async def execute(self, context: AbilityExecutionContext) -> ActionResult:
        """执行任务终止。

        优先使用 last_action_result 的内容作为最终回复；
        如果没有，则从 accumulated_data 中生成摘要。

        Args:
            context: 执行上下文

        Returns:
            ActionResult，data 中包含 "response" 字段
        """
        response = self._collect_response(context)

        logger.debug(f"EndTaskAbility: ending task with response ({len(response)} chars)")

        return ActionResult(
            outcome=ActionOutcome.SUCCESS,
            data={"response": response},
            next_action_hint=None,  # 明确结束
        )

    def _collect_response(self, context: AbilityExecutionContext) -> str:
        """从上下文中收集最终回复内容。

        优先级：
        1. last_action_result 中的 response/content
        2. accumulated_data 中的 response
        3. 默认的 "Task completed" 消息

        Args:
            context: 执行上下文

        Returns:
            最终回复文本
        """
        # 优先级 1：从 last_action_result 提取
        if context.last_action_result is not None:
            ar = context.last_action_result
            response = ar.data.get("response", ar.data.get("content", ""))
            if response:
                return response

        # 优先级 2：从 accumulated_data 提取
        response = context.accumulated_data.get("response", "")
        if response:
            return response

        # 优先级 3：默认回复
        return "Task completed"
