# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ToolCallFoldStrategy：ToolCall 折叠策略。

压缩冗长的工具调用返回（ToolResultBlock），减少单条消息的体积。

行为：
- 识别 role="tool" 消息中的 ToolResultBlock，如果 content 超过阈值，截断并添加省略标记
- AI 消息的 tool_calls 保持不变（保留函数名和参数等关键信息）
- 不改变消息数量，只压缩单条消息体积

适用场景：工具返回大量数据（如文件内容、API 响应）时压缩。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ghrah.context.window import WindowStrategy
from ghrah.core.window_protocol import MessageFactory, WindowableMessage

if TYPE_CHECKING:
    from ghrah.core.window_protocol import WindowableBlock

__all__ = ["ToolCallFoldStrategy", "fold_tool_result_content", "tool_message_needs_fold"]

# 默认截断长度
_DEFAULT_MAX_CONTENT_LENGTH = 500

# 截断后缀模板
_TRUNCATION_SUFFIX = "\n...[truncated, original: {length} chars]"


def fold_tool_result_content(content: str, max_length: int) -> str:
    """截断超长工具结果正文并加省略标记（纯函数）。

    Args:
        content: 原始 ToolResultBlock content
        max_length: 最大字符长度

    Returns:
        超长时为前 max_length 字符 + 截断后缀；未超长返回原文
    """
    if len(content) <= max_length:
        return content
    suffix = _TRUNCATION_SUFFIX.format(length=len(content))
    return content[:max_length] + suffix


def tool_message_needs_fold(msg: WindowableMessage, max_length: int) -> bool:
    """判定 role="tool" 消息是否含超长 ToolResultBlock（纯函数）。

    Args:
        msg: 待判定消息
        max_length: 最大字符长度

    Returns:
        是否需要折叠
    """
    for block in msg.content_blocks:
        if (
            getattr(block, "type", None) == "tool_result"
            and len(getattr(block, "content", "")) > max_length
        ):
            return True
    return False


class ToolCallFoldStrategy(WindowStrategy):
    """ToolCall 折叠策略 — 压缩冗长的工具调用返回。

    行为：
    - 识别 role="tool" 消息中 content 过长的 ToolResultBlock，截断并添加省略标记
    - AI 消息的 tool_calls 保持不变
    - 不改变消息数量，只压缩单条消息体积

    适用场景：工具返回大量数据时压缩。

    Args:
        max_content_length: ToolResultBlock content 的最大字符长度，默认 500
        message_factory: 消息构造工厂，用于构造折叠后的新消息
    """

    def __init__(
        self,
        max_content_length: int = _DEFAULT_MAX_CONTENT_LENGTH,
        message_factory: MessageFactory | None = None,
    ) -> None:
        if max_content_length <= 0:
            raise ValueError(f"max_content_length must be positive, got {max_content_length}")
        self._max_content_length = max_content_length
        self._message_factory = message_factory

    @property
    def max_content_length(self) -> int:
        """最大 content 长度。"""
        return self._max_content_length

    async def apply(
        self, messages: list[WindowableMessage], token_budget: int
    ) -> list[WindowableMessage]:
        """应用 ToolCall 折叠策略。

        Args:
            messages: 输入消息列表
            token_budget: token 预算（此策略不使用此参数，仅保留接口一致）

        Returns:
            折叠后的消息列表
        """
        result: list[WindowableMessage] = []
        for msg in messages:
            if msg.role == "tool":
                folded = self._fold_tool_message(msg)
                result.append(folded)
            else:
                result.append(msg)
        return result

    def _fold_tool_message(self, msg: WindowableMessage) -> WindowableMessage:
        """折叠 role="tool" 消息中的 ToolResultBlock。

        如果 content 超过 max_content_length，截断并添加省略标记。

        Args:
            msg: 原始 WindowableMessage (role="tool")

        Returns:
            折叠后的 WindowableMessage（如果需要折叠），或原始消息
        """
        if not tool_message_needs_fold(msg, self._max_content_length):
            return msg

        if self._message_factory is None:
            return msg

        new_blocks: list[WindowableBlock] = []
        for block in msg.content_blocks:
            if getattr(block, "type", None) == "tool_result":
                content = getattr(block, "content", "")
                if len(content) > self._max_content_length:
                    new_blocks.append(
                        self._message_factory.create_tool_result_block(
                            tool_call_id=getattr(block, "tool_call_id", ""),
                            name=getattr(block, "name", None),
                            content=fold_tool_result_content(content, self._max_content_length),
                            success=getattr(block, "success", True),
                            error=getattr(block, "error", None),
                        )
                    )
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)

        return self._message_factory.create_message(
            role=msg.role,
            content_blocks=new_blocks,
            source=msg.source,
            metadata=msg.metadata,
        )

    @property
    def name(self) -> str:
        """策略名称。"""
        return "tool_call_fold"
