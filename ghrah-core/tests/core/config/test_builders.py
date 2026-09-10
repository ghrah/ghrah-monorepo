# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""core/config/builders 窗口配置构建测试。

覆盖 DEFAULT_WINDOW_MAX_TOKENS 默认值兜底与显式覆盖优先（工作流 B / D3）。
"""

from ghrah.core.config.builders import build_window_from_dict, build_window_from_overrides
from ghrah.manifest.agent import WindowOverrides
from ghrah.types.config_types import DEFAULT_WINDOW_MAX_TOKENS


class TestBuildWindowFromDict:
    """wire payload → WindowConfig。"""

    def test_default_max_tokens(self) -> None:
        """未设 max_tokens 时兜底 DEFAULT_WINDOW_MAX_TOKENS（32768）。"""
        config = build_window_from_dict({})

        assert config.max_tokens == DEFAULT_WINDOW_MAX_TOKENS
        assert config.max_tokens == 32768

    def test_explicit_max_tokens_overrides_default(self) -> None:
        """显式 max_tokens 优先于默认值。"""
        config = build_window_from_dict({"max_tokens": 8192})

        assert config.max_tokens == 8192


class TestBuildWindowFromOverrides:
    """manifest WindowOverrides → WindowConfig。"""

    def test_default_max_tokens_when_none(self) -> None:
        """max_tokens 未声明（None）时兜底 DEFAULT_WINDOW_MAX_TOKENS（32768）。"""
        config = build_window_from_overrides(WindowOverrides())

        assert config.max_tokens == DEFAULT_WINDOW_MAX_TOKENS
        assert config.max_tokens == 32768

    def test_explicit_max_tokens_overrides_default(self) -> None:
        """显式 max_tokens 优先于默认值。"""
        config = build_window_from_overrides(WindowOverrides(max_tokens=4096))

        assert config.max_tokens == 4096
