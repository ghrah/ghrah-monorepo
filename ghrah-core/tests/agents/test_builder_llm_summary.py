# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""AgentBuilder llm_summary 工厂注入与 reset 重注入测试。

覆盖：
- from_config 将 llm_factory 透传为 llm_summary 策略的惰性工厂回调
- _ensure_llm() 后回填显式 LLM（happy path 摘要真实发生）
- reset() 重建 ContextManager 后 LLM 被重新回填
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ghrah.agents.builder import AgentBuilder
from ghrah.types.config_types import AgentConfig, WindowConfig


def _fake_llm() -> MagicMock:
    llm = MagicMock()
    llm.model = "fake-model"
    llm.generate = AsyncMock()
    llm.configure_tools = MagicMock()
    return llm


def _config() -> AgentConfig:
    return AgentConfig(
        name="test-agent",
        window=WindowConfig(strategies=["llm_summary"], max_tokens=4096),
    )


def _summary_strategy(agent: Any) -> Any:
    from ghrah.context.strategies.llm_summary import LLMSummaryStrategy

    return next(
        s
        for s in agent._context_manager.window_manager.strategies
        if isinstance(s, LLMSummaryStrategy)
    )


class TestBuilderLLMFactoryWiring:
    """from_config 的 llm_summary 工厂装配。"""

    def test_summary_strategy_holds_lazy_factory(self) -> None:
        """策略持有惰性工厂回调（首次 apply 才解析），且工厂收到 AgentConfig。"""
        fake_llm = _fake_llm()
        factory = MagicMock(return_value=fake_llm)
        config = _config()

        agent = AgentBuilder.from_config(config, llm_factory=factory)

        strategy = _summary_strategy(agent)
        assert strategy.llm is None
        assert strategy._llm_factory is not None
        assert strategy._llm_factory() is fake_llm
        factory.assert_called_once_with(config)

    @pytest.mark.asyncio
    async def test_ensure_llm_backfills_summary_strategy(self) -> None:
        """_ensure_llm 创建 LLM 后回填策略（避免工厂重复创建客户端）。"""
        fake_llm = _fake_llm()
        factory = MagicMock(return_value=fake_llm)

        agent = AgentBuilder.from_config(_config(), llm_factory=factory)
        await agent._ensure_llm()

        assert _summary_strategy(agent).llm is fake_llm

    @pytest.mark.asyncio
    async def test_reset_reinjects_summary_llm(self) -> None:
        """reset 重建 ContextManager 后，已缓存的 LLM 被重新回填。"""
        fake_llm = _fake_llm()
        factory = MagicMock(return_value=fake_llm)

        agent = AgentBuilder.from_config(_config(), llm_factory=factory)
        await agent._ensure_llm()
        await agent.reset()

        assert _summary_strategy(agent).llm is fake_llm
