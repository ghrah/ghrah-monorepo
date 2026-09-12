# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""模型窗口表与预算来源解析测试。"""

from __future__ import annotations

from ghrah.context.model_windows import lookup_model_window
from ghrah.context.window import WindowManager
from ghrah.types.config_types import DEFAULT_WINDOW_MAX_TOKENS


class TestLookupModelWindow:
    def test_exact_family_prefix(self) -> None:
        assert lookup_model_window("claude-sonnet-4-20250514") == 200_000
        assert lookup_model_window("gpt-4o") == 128_000
        assert lookup_model_window("deepseek-chat") == 128_000

    def test_longest_prefix_wins(self) -> None:
        # gpt-4 系短前缀不应吃掉 gpt-4o/gpt-4.1 的长前缀
        assert lookup_model_window("gpt-4o-mini-2024-07-18") == 128_000
        assert lookup_model_window("gpt-4.1-2025-04-14") == 1_047_576
        assert lookup_model_window("gpt-4-turbo") == 128_000
        # claude-3-5-haiku 优于 claude-3-5 与 claude
        assert lookup_model_window("claude-3-5-haiku-20241022") == 200_000

    def test_case_insensitive_and_whitespace(self) -> None:
        assert lookup_model_window("  Claude-Sonnet-4  ") == 200_000
        assert lookup_model_window("DeepSeek-Reasoner") == 128_000

    def test_unknown_model_returns_none(self) -> None:
        assert lookup_model_window("some-unknown-model") is None
        assert lookup_model_window("") is None
        assert lookup_model_window("   ") is None


class TestWindowManagerBudgetSource:
    def test_declared_budget(self) -> None:
        wm = WindowManager(max_tokens=8192)
        assert wm.max_tokens == 8192
        assert wm.max_tokens_source == "declared"

    def test_undeclared_falls_back_to_default(self) -> None:
        wm = WindowManager()
        assert wm.max_tokens == DEFAULT_WINDOW_MAX_TOKENS
        assert wm.max_tokens_source == "default"

    def test_resolve_from_model_table(self) -> None:
        wm = WindowManager()
        assert wm.resolve_budget_from_model("claude-sonnet-4-20250514") is True
        assert wm.max_tokens == 200_000
        assert wm.max_tokens_source == "model_table"

    def test_resolve_unknown_model_keeps_default(self) -> None:
        wm = WindowManager()
        assert wm.resolve_budget_from_model("mystery-model") is False
        assert wm.max_tokens == DEFAULT_WINDOW_MAX_TOKENS
        assert wm.max_tokens_source == "default"

    def test_resolve_idempotent_after_table_hit(self) -> None:
        wm = WindowManager()
        wm.resolve_budget_from_model("gpt-4o")
        # 已落定后再次调用不动
        assert wm.resolve_budget_from_model("gpt-4.1") is False
        assert wm.max_tokens == 128_000
        assert wm.max_tokens_source == "model_table"

    def test_declared_not_overridden_by_table(self) -> None:
        wm = WindowManager(max_tokens=1000)
        assert wm.resolve_budget_from_model("gpt-4o") is False
        assert wm.max_tokens == 1000
        assert wm.max_tokens_source == "declared"

