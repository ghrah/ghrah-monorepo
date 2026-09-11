# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""LLMSummaryStrategy：LLM 摘要策略。

使用 LLM 总结旧消息，用一条摘要消息替代大量历史对话，
从而减少 token 数量，同时保留关键语义信息。

行为：
- 将消息分为"旧消息"和"新消息"
- 对"旧消息"使用 LLM 生成摘要
- 用一条 system 消息替代旧消息（标记为上下文摘要）
- 新消息保持不变
- LLM 调用失败时回退到简单截断（保留最新消息）

适用场景：长对话场景，需要保留对话语义但减少 token 数。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ghrah.context.compact import SUMMARY_MESSAGE_PREFIX
from ghrah.context.window import WindowStrategy, _split_system_messages, estimate_tokens
from ghrah.core.window_protocol import (
    MessageFactory,
    SummaryLLMProtocol,
    WindowableMessage,
)

__all__ = ["LLMSummaryStrategy", "format_messages_for_summary", "get_role_label"]

logger = logging.getLogger(__name__)

# 默认摘要提示词
_DEFAULT_SUMMARY_PROMPT = (
    "Please summarize the following conversation concisely, "
    "preserving key facts, decisions, and any important context. "
    "Write the summary in the same language as the conversation."
)

# 摘要消息前缀（单一来源在 ghrah.context.compact）
_SUMMARY_PREFIX = SUMMARY_MESSAGE_PREFIX


def get_role_label(msg: WindowableMessage) -> str:
    """获取消息的角色标签（纯函数，compact/recall 复用）。

    Args:
        msg: WindowableMessage 对象

    Returns:
        角色标签字符串
    """
    if msg.role == "system":
        return "System"
    elif msg.role == "user":
        return "Human"
    elif msg.role == "ai":
        return "AI"
    elif msg.role == "tool":
        tool_results = msg.tool_results
        if tool_results:
            name = getattr(tool_results[0], "name", None) or "unknown"
            return f"Tool({name})"
        return "Tool"
    else:
        return "Unknown"


def format_messages_for_summary(messages: list[WindowableMessage]) -> str:
    """将消息列表格式化为摘要用的文本（纯函数，compact/recall 复用）。

    Args:
        messages: 消息列表

    Returns:
        格式化后的文本
    """
    lines: list[str] = []
    for msg in messages:
        role = get_role_label(msg)
        content = msg.text
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


class LLMSummaryStrategy(WindowStrategy):
    """LLM 摘要策略 — 用 LLM 总结旧消息。

    行为：
    - 如果总 token 在预算内，不生成摘要
    - 将非 system 消息分为"旧"和"新"（3/4 预算分给新消息）
    - 对旧消息调用 LLM 生成摘要（失败重试一次，仍失败回退截断）
    - 用一条 system 消息替代旧消息
    - 摘要事件可经 drain_compaction_record() 取出，供节点 metadata 审计

    适用场景：长对话场景，需要保留对话语义但减少 token 数。

    LLM 解析顺序（惰性）：
    1. 显式注入的 llm（set_llm / 构造参数）优先
    2. llm_factory 回调（首次调用结果 memoize；工厂抛异常时告警并回退截断，
       不缓存失败）

    Args:
        llm: 满足 SummaryLLMProtocol 的 LLM 实例（可选，优先于 llm_factory）
        summary_prompt: 摘要提示词（可选，使用默认提示词）
        message_factory: 消息构造工厂，用于构造摘要消息和 LLM 输入消息
        llm_factory: 零参 LLM 工厂回调（可选；用于策略装配先于 LLM 创建的
            时序解耦，在首次需要时惰性解析）
    """

    skip_when_under_budget = True

    def __init__(
        self,
        llm: SummaryLLMProtocol | None = None,
        summary_prompt: str | None = None,
        message_factory: MessageFactory | None = None,
        llm_factory: Callable[[], SummaryLLMProtocol] | None = None,
    ) -> None:
        self._llm = llm
        self._summary_prompt = summary_prompt or _DEFAULT_SUMMARY_PROMPT
        self._message_factory = message_factory
        self._llm_factory = llm_factory
        self._factory_llm: SummaryLLMProtocol | None = None
        self._last_compaction: dict[str, Any] | None = None

    @property
    def summary_prompt(self) -> str:
        """摘要提示词。"""
        return self._summary_prompt

    async def apply(
        self, messages: list[WindowableMessage], token_budget: int
    ) -> list[WindowableMessage]:
        """应用 LLM 摘要策略。

        Args:
            messages: 输入消息列表
            token_budget: token 预算

        Returns:
            压缩后的消息列表
        """
        # 如果已在预算内，直接返回
        current_tokens = estimate_tokens(messages)
        if current_tokens <= token_budget:
            return list(messages)

        system_msgs, other_msgs = _split_system_messages(messages)

        if not other_msgs:
            return list(messages)

        # 计算分割点：3/4 预算分给新消息
        system_tokens = estimate_tokens(system_msgs)
        remaining_budget = token_budget - system_tokens
        new_budget = int(remaining_budget * 0.75)

        # 从尾部开始累积，确定"新消息"范围
        split_index = self._find_split_index(other_msgs, new_budget)

        # 如果所有消息都是"新消息"，无法生成摘要，直接返回
        if split_index <= 0:
            return system_msgs + other_msgs

        old_msgs = other_msgs[:split_index]
        new_msgs = other_msgs[split_index:]

        # 生成摘要
        summary_msg = await self._generate_summary(old_msgs)

        if summary_msg is not None:
            result = system_msgs + [summary_msg] + new_msgs
            self._last_compaction = {
                "strategy": self.name,
                "summarized_messages": len(old_msgs),
                "tokens_before": current_tokens,
                "tokens_after": estimate_tokens(result),
                "summary": summary_msg.text,
            }
            logger.info(
                "LLMSummaryStrategy compacted %d messages (%d -> %d tokens)",
                len(old_msgs),
                current_tokens,
                self._last_compaction["tokens_after"],
            )
            return result
        else:
            # LLM 调用失败，回退到简单截断（只保留新消息）
            logger.warning("LLM summary failed, falling back to truncation")
            return system_msgs + new_msgs

    def _find_split_index(self, messages: list[WindowableMessage], new_budget: int) -> int:
        """找到分割点：从尾部累积消息直到超过 new_budget。

        返回旧消息的结束索引（新消息从 split_index 开始）。

        Args:
            messages: 非 system 消息列表
            new_budget: 新消息的 token 预算

        Returns:
            分割索引
        """
        cumulative = 0
        split_index = len(messages)

        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = estimate_tokens([messages[i]])
            cumulative += msg_tokens
            if cumulative > new_budget:
                # 当前消息也属于旧消息
                split_index = i + 1
                break
            split_index = i

        return split_index

    async def _generate_summary(
        self, old_messages: list[WindowableMessage]
    ) -> WindowableMessage | None:
        """调用 LLM 生成旧消息的摘要。

        Args:
            old_messages: 要总结的消息列表

        Returns:
            摘要消息（role="system"），失败返回 None
        """
        # 格式化旧消息为文本
        conversation_text = self._format_messages_for_summary(old_messages)

        if not conversation_text.strip():
            return None

        llm = self._resolve_llm()

        if llm is None:
            logger.warning("LLMSummaryStrategy has no LLM configured, skipping summary")
            return None

        if self._message_factory is None:
            logger.warning("LLMSummaryStrategy has no message_factory configured, skipping summary")
            return None

        summary_messages = [
            self._message_factory.create_message(
                role="system",
                text=self._summary_prompt,
            ),
            self._message_factory.create_message(
                role="user",
                text=conversation_text,
            ),
        ]

        summary_content: str | None = None
        for attempt in (1, 2):
            try:
                response = await llm.generate(summary_messages)
                summary_content = response.text or ""
                break
            except Exception:
                logger.warning("LLM summary generate attempt %d/2 failed", attempt, exc_info=True)

        if summary_content is None:
            return None

        return self._message_factory.create_message(
            role="system",
            text=_SUMMARY_PREFIX + summary_content,
        )

    def _resolve_llm(self) -> SummaryLLMProtocol | None:
        """按解析顺序获取 LLM：显式注入优先，其次 llm_factory 惰性解析。

        factory 成功结果 memoize；factory 抛异常时告警且不缓存失败，
        下次 apply 会重试解析。

        Returns:
            可用的 LLM 实例，无法解析时返回 None
        """
        if self._llm is not None:
            return self._llm

        if self._llm_factory is None:
            return None

        if self._factory_llm is None:
            try:
                self._factory_llm = self._llm_factory()
            except Exception:
                logger.exception(
                    "LLMSummaryStrategy llm_factory failed, falling back to truncation"
                )
                return None

        return self._factory_llm

    def _format_messages_for_summary(self, messages: list[WindowableMessage]) -> str:
        """将消息列表格式化为摘要用的文本（委托模块级纯函数）。

        Args:
            messages: 消息列表

        Returns:
            格式化后的文本
        """
        return format_messages_for_summary(messages)

    def _get_role_label(self, msg: WindowableMessage) -> str:
        """获取消息的角色标签（委托模块级纯函数）。

        Args:
            msg: WindowableMessage 对象

        Returns:
            角色标签字符串
        """
        return get_role_label(msg)

    @property
    def llm(self) -> SummaryLLMProtocol | None:
        return self._llm

    def set_llm(self, llm: SummaryLLMProtocol) -> None:
        self._llm = llm

    def drain_compaction_record(self) -> dict[str, Any] | None:
        """取出并清空最近一次成功摘要的 compaction 事件记录。

        Returns:
            记录 dict（strategy/summarized_messages/tokens_before/tokens_after/summary），
            无未取出的记录时返回 None
        """
        record = self._last_compaction
        self._last_compaction = None
        return record

    @property
    def name(self) -> str:
        """策略名称。"""
        return "llm_summary"
