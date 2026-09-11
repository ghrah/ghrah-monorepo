# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""链上 compact 引擎（ghrah.builtin 综合方法）的纯函数与常量集合。

ghrah.builtin 内部阶段固定、不可再组合：
①按节点边界分割（保留窗 = 尾部 compact_keep_recent 个节点，摘要窗 = 其余）
②摘要窗内长工具输出确定性折叠
③折叠后整理结果请求 LLM 生成摘要（失败降级为确定性折叠视图）
④快照拼接 = [system(session), 前置提示消息, 摘要消息, 保留窗消息…]

本模块只承载纯逻辑与提示词常量；事务编排（LLM 调用、节点提交、事件发布）
在 ActorAgent._run_compact_round 与 ContextManager.commit_compact_node。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ghrah.context.window import estimate_tokens

if TYPE_CHECKING:
    from ghrah.context.node import ContextNode
    from ghrah.core.window_protocol import MessageFactory, WindowableMessage

__all__ = [
    "COMPACT_DEGRADED_PREAMBLE",
    "COMPACT_PREAMBLE_TEMPLATE",
    "COMPACT_SUMMARY_PROMPT",
    "SUMMARY_MESSAGE_PREFIX",
    "assemble_snapshot",
    "collect_window_messages",
    "fold_long_tool_outputs",
    "is_compact_node",
    "post_check_snapshot",
    "split_compact_windows",
    "truncate_summary_input",
]

# 摘要消息统一前缀（链上 compact 与 LLMSummaryStrategy 共用，单一来源）
SUMMARY_MESSAGE_PREFIX = "[Context Summary] "

# 摘要提示词（引擎内置常量，TODO: manifest 定制出口）
COMPACT_SUMMARY_PROMPT = (
    "You are compacting the earlier history of a multi-agent conversation. "
    "Summarize the following records concisely, preserving key facts, decisions, "
    "open tasks, and any important context — including any earlier summaries "
    "(absorb them; do not nest or stack summaries). Write the summary in the "
    "same language as the conversation."
)

# 快照前置提示模板（正常路径）：注入点，提及 recall_context 与压缩范围
COMPACT_PREAMBLE_TEMPLATE = (
    "Note: the earlier conversation history has been compacted into the summary "
    "below. The full original messages remain on the action chain and can be "
    "queried with the `recall_context` ability (summarized range: nodes "
    "{summarized_range})."
)

# 降级路径前置提示（LLM 摘要失败时的确定性折叠视图）
COMPACT_DEGRADED_PREAMBLE = (
    "Note: the earlier conversation history has been compacted. Long tool "
    "outputs were truncated; the records below are the compacted earlier "
    "history in order."
)


def is_compact_node(node: ContextNode) -> bool:
    """判定节点是否为链上 compact 节点。"""
    return bool(node.metadata.get("node_kind") == "compact")


def split_compact_windows(
    history: list[ContextNode], keep_recent: int
) -> tuple[list[ContextNode], list[ContextNode]] | None:
    """按节点边界把链历史分割为摘要窗与保留窗。

    Args:
        history: 链历史（根在前）
        keep_recent: 保留窗节点数（含 compact 节点，按节点数保守计数）

    Returns:
        (摘要窗节点, 保留窗节点)；root 之外的可压缩节点不足 keep_recent+1
        （即窗外为空）时返回 None——防每轮触发振荡
    """
    compressible = history[1:]  # root 恒不参与压缩
    if len(compressible) <= keep_recent:
        return None
    summary_nodes = compressible[:-keep_recent]
    kept_nodes = compressible[-keep_recent:]
    return summary_nodes, kept_nodes


def collect_window_messages(
    summary_nodes: list[ContextNode], kept_nodes: list[ContextNode]
) -> tuple[list[Any], list[Any]]:
    """从窗口节点重组摘要侧与保留侧消息。

    规则（吸收不堆叠）：
    - 普通节点 delta 全收（保留侧过滤 role="system"——system 由 session
      prompt 重建置首）；
    - 链上 compact 节点 delta 恒空、内容在 snapshot：无论落在哪个窗，其
      摘要消息（SUMMARY_MESSAGE_PREFIX 置首的 system 消息）一律归摘要侧
      输入（摘要窗吸收上一份摘要），前置提示消息丢弃；保留窗只收普通
      节点 delta——否则会出现 snapshot 展开重复或双份摘要堆叠。

    Returns:
        (摘要侧消息, 保留侧消息)，均按链序
    """
    summary_messages: list[Any] = []
    kept_messages: list[Any] = []

    for node in summary_nodes:
        if is_compact_node(node) and node.messages_snapshot is not None:
            # 吸收上一份摘要：snapshot 中带前缀的 system 消息进摘要输入
            for msg in node.messages_snapshot:
                text = getattr(msg, "text", "") or ""
                if msg.role == "system" and text.startswith(SUMMARY_MESSAGE_PREFIX):
                    summary_messages.append(msg)
        else:
            summary_messages.extend(
                msg for msg in node.messages_delta if getattr(msg, "role", None) != "system"
            )

    for node in kept_nodes:
        if not is_compact_node(node):
            kept_messages.extend(
                msg for msg in node.messages_delta if getattr(msg, "role", None) != "system"
            )

    return summary_messages, kept_messages


def fold_long_tool_outputs(
    messages: list[WindowableMessage], max_length: int, message_factory: MessageFactory | None
) -> list[WindowableMessage]:
    """对消息列表中 role="tool" 的超长工具输出做确定性折叠。

    Args:
        messages: 待折叠消息
        max_length: 单条 ToolResultBlock content 最大字符长度
        message_factory: 消息构造工厂（None 时原样返回，与策略行为一致）

    Returns:
        折叠后的消息列表
    """
    if message_factory is None:
        return list(messages)

    from ghrah.context.strategies.tool_call_fold import (
        fold_tool_result_content,
        tool_message_needs_fold,
    )

    result: list[WindowableMessage] = []
    for msg in messages:
        if msg.role != "tool" or not tool_message_needs_fold(msg, max_length):
            result.append(msg)
            continue
        new_blocks: list[Any] = []
        for block in msg.content_blocks:
            if getattr(block, "type", None) == "tool_result":
                content = getattr(block, "content", "")
                if len(content) > max_length:
                    new_blocks.append(
                        message_factory.create_tool_result_block(
                            tool_call_id=getattr(block, "tool_call_id", ""),
                            name=getattr(block, "name", None),
                            content=fold_tool_result_content(content, max_length),
                            success=getattr(block, "success", True),
                            error=getattr(block, "error", None),
                        )
                    )
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)
        result.append(
            message_factory.create_message(
                role=msg.role,
                content_blocks=new_blocks,
                source=msg.source,
                metadata=msg.metadata,
            )
        )
    return result


def truncate_summary_input(
    messages: list[WindowableMessage], budget: int
) -> tuple[list[WindowableMessage], bool]:
    """摘要输入体积安全：超 budget×2 时渐进丢弃最旧消息并加标记。

    budget×2 是"模型可发送规模"的代理阈值（输入+输出同算）。

    Args:
        messages: 折叠后的摘要侧消息
        budget: 声明 token 预算

    Returns:
        (截断后消息, 是否发生过截断)
    """
    limit = budget * 2
    if estimate_tokens(messages) <= limit:
        return messages, False
    kept = list(messages)
    while kept and estimate_tokens(kept) > limit:
        kept.pop(0)
    return kept, True


def assemble_snapshot(
    system_prompt: str,
    preamble_text: str,
    summary_text: str | None,
    kept_messages: list[WindowableMessage],
    message_factory: MessageFactory,
) -> list[WindowableMessage]:
    """拼接 compact 快照视图。

    布局：[system(session), 前置提示消息, 摘要消息, 保留窗消息…]。
    summary_text 为 None 时是降级路径——折叠后的摘要侧消息原样插入
    前置提示之后（由调用方先行折叠并拼接 kept_messages 之前），本函数
    只负责头部三条的组装由调用方控制；正常路径 summary_text 非空。

    Args:
        system_prompt: 当前 session 的 system prompt（可空串，空串时省略首条）
        preamble_text: 前置提示正文（注入点）
        summary_text: LLM 摘要文本（None = 降级路径，摘要段由调用方提供）
        kept_messages: 保留窗消息
        message_factory: 消息构造工厂

    Returns:
        快照消息列表
    """
    snapshot: list[WindowableMessage] = []
    if system_prompt:
        snapshot.append(message_factory.create_message(role="system", text=system_prompt))
    snapshot.append(
        message_factory.create_message(role="system", text=preamble_text, source="system:runtime")
    )
    if summary_text is not None:
        snapshot.append(
            message_factory.create_message(
                role="system",
                text=SUMMARY_MESSAGE_PREFIX + summary_text,
                source="system:runtime",
            )
        )
    snapshot.extend(kept_messages)
    return snapshot


def post_check_snapshot(
    snapshot: list[WindowableMessage], budget: int, message_factory: MessageFactory
) -> tuple[list[WindowableMessage], str]:
    """提交前自检：估算快照体积超预算时截断摘要文本（保留窗为地板）。

    Args:
        snapshot: 待自检快照（布局：system/preamble/summary/kept…，
            摘要消息为可选第 3 条，识别特征 SUMMARY_MESSAGE_PREFIX 置首）
        budget: token 预算（估算口径 chars/4，非承重）
        message_factory: 消息构造工厂

    Returns:
        (处理后的快照, 状态)，状态为 "ok" 或 "over_budget"。摘要文本截断
        至预算余量；保留窗不缩减（keep_recent≥2 为地板）。终态仍超预算
        （病理：system + 2 轮 > 预算）时原样返回并标 over_budget。
    """
    if estimate_tokens(snapshot) <= budget:
        return snapshot, "ok"

    summary_index = next(
        (
            i
            for i, msg in enumerate(snapshot)
            if msg.role == "system"
            and (getattr(msg, "text", "") or "").startswith(SUMMARY_MESSAGE_PREFIX)
        ),
        None,
    )
    if summary_index is None:
        # 降级快照无摘要消息可截——按 over_budget 提交（保留窗是地板）
        return snapshot, "over_budget"

    overhead = estimate_tokens(snapshot) - estimate_tokens([snapshot[summary_index]])
    remaining = budget - overhead
    if remaining <= 0:
        return snapshot, "over_budget"

    # 估算口径下 chars ≈ tokens×4；截到余量后重估，必要时再收紧一轮
    summary_text = snapshot[summary_index].text
    truncated = summary_text[: max(remaining * 4, 0)]
    new_snapshot = list(snapshot)
    new_snapshot[summary_index] = message_factory.create_message(
        role="system", text=truncated, source="system:runtime"
    )
    if estimate_tokens(new_snapshot) <= budget:
        return new_snapshot, "ok"

    # 一次截断不够（块级计数有下限）：按字符贪心收紧至预算内或枯竭
    while remaining > 0:
        remaining -= max(1, estimate_tokens(new_snapshot) - budget)
        truncated = truncated[: max(remaining * 4, 0)]
        if not truncated:
            break
        new_snapshot[summary_index] = message_factory.create_message(
            role="system", text=truncated, source="system:runtime"
        )
        if estimate_tokens(new_snapshot) <= budget:
            return new_snapshot, "ok"
    return new_snapshot, "over_budget"
