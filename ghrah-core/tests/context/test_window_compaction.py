# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""窗口压缩（compaction）集成测试。

覆盖 ContextManager 与 LLMSummaryStrategy 的端到端行为（工作流 B 验收）：
- 超预算时真实触发 LLM 摘要，早期事实进入摘要输入
- commit_iteration 将 compaction 事件写入节点 metadata
- rollback_iteration 清空未提交的 compaction 记录
- 超预算长会话持续多轮后，上下文仍在预算内且摘要保留早期事实
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ghrah.chat.factory import ChatMessageFactory
from ghrah.chat.message import ChatMessage
from ghrah.context.manager import ContextManager
from ghrah.context.strategies.llm_summary import LLMSummaryStrategy
from ghrah.context.window import WindowManager, estimate_tokens


class _RecordingLLM:
    """捕获摘要输入的假 LLM（满足 SummaryLLMProtocol）。"""

    def __init__(self, summary_text: str = "Summary of earlier conversation.") -> None:
        self.summary_text = summary_text
        self.prompts: list[str] = []
        self.calls = 0

    async def generate(self, messages: list[Any], tools: list[dict[str, Any]] | None = None) -> Any:
        self.calls += 1
        self.prompts.append(messages[-1].text)
        return SimpleNamespace(text=self.summary_text)


def _human(content: str) -> ChatMessage:
    return ChatMessage.user(text_or_blocks=content)


def _make_cm(max_tokens: int) -> tuple[ContextManager, _RecordingLLM]:
    """构建带 llm_summary 策略的 ContextManager 及其假 LLM。"""
    llm = _RecordingLLM()
    msg_factory = ChatMessageFactory()
    strategy = LLMSummaryStrategy(llm=llm, message_factory=msg_factory)
    window_manager = WindowManager(strategies=[strategy], max_tokens=max_tokens)
    cm = ContextManager(
        agent_name="test-agent",
        initial_state={},
        system_prompt="system prompt",
        window_manager=window_manager,
        message_factory=msg_factory,
    )
    return cm, llm


def _seed_history(cm: ContextManager, rounds: int = 1) -> None:
    """写入包含早期事实的超预算历史。"""
    cm.begin_iteration()
    cm.add_messages(
        [_human(f"EARLY-FACT-{i} mystery word is zebra " + "x" * 150) for i in range(10)]
    )
    cm.commit_iteration(ability_names=["seed"])
    for r in range(rounds):
        cm.begin_iteration()
        cm.add_messages([_human(f"round-{r} " + "y" * 200)])
        cm.commit_iteration(ability_names=["fill"])


class TestCompactionAuditability:
    """compaction 事件写入节点 metadata。"""

    @pytest.mark.asyncio
    async def test_commit_iteration_writes_compaction_metadata(self) -> None:
        """超预算触发摘要后，事件记录随 commit 写入节点 metadata。"""
        cm, llm = _make_cm(max_tokens=300)
        _seed_history(cm)

        cm.begin_iteration()
        messages = await cm.get_llm_messages()

        assert llm.calls == 1
        assert any("EARLY-FACT-0" in p and "zebra" in p for p in llm.prompts)
        summary_msgs = [m for m in messages if m.role == "system" and "[Context Summary]" in m.text]
        assert len(summary_msgs) == 1

        node = cm.commit_iteration(ability_names=["talk"])

        assert "compaction" in node.metadata
        record = node.metadata["compaction"][0]
        assert record["strategy"] == "llm_summary"
        assert record["summarized_messages"] > 0
        assert record["tokens_before"] > record["tokens_after"]
        assert record["summary"].startswith("[Context Summary] ")

    @pytest.mark.asyncio
    async def test_rollback_clears_pending_compaction(self) -> None:
        """回滚迭代后未提交的 compaction 记录被清空。"""
        cm, _ = _make_cm(max_tokens=300)
        _seed_history(cm)

        cm.begin_iteration()
        await cm.get_llm_messages()
        cm.rollback_iteration(RuntimeError("boom"))
        cm.begin_iteration()
        node = cm.commit_iteration(ability_names=["retry"])

        assert "compaction" not in node.metadata

    @pytest.mark.asyncio
    async def test_no_summary_no_compaction_metadata(self) -> None:
        """预算内不触发摘要，节点 metadata 无 compaction 键。"""
        cm, llm = _make_cm(max_tokens=10000)

        cm.begin_iteration()
        cm.add_messages([_human("short message")])
        await cm.get_llm_messages()
        node = cm.commit_iteration(ability_names=["talk"])

        assert llm.calls == 0
        assert "compaction" not in node.metadata


class TestLongSessionEarlyFacts:
    """B 验收主用例：超预算长会话持续多轮后早期事实仍可达 LLM。"""

    @pytest.mark.asyncio
    async def test_early_facts_reach_summary_and_context_stays_in_budget(self) -> None:
        """多轮超预算迭代：每轮真实摘要、输出在预算内、早期事实进入摘要输入。"""
        cm, llm = _make_cm(max_tokens=400)
        _seed_history(cm, rounds=3)

        for _ in range(3):
            cm.begin_iteration()
            cm.add_messages([_human("turn " + "z" * 200)])
            messages = await cm.get_llm_messages()

            assert estimate_tokens(messages) <= 400
            assert any(m.role == "system" and "[Context Summary]" in m.text for m in messages)
            cm.commit_iteration(ability_names=["talk"])

        assert llm.calls == 3
        assert any("EARLY-FACT-0" in p and "zebra" in p for p in llm.prompts)
