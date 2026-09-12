# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Token 用量类型 — 纯数据定义，零内部依赖。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TokenUsage:
    """LLM 调用的 token 用量。

    归一化口径：``input_tokens`` 恒为**总输入**（含缓存命中与缓存写入部分），
    各厂商语义在此对齐——Anthropic 侧解析时将 ``input + cache_read +
    cache_write`` 计入 ``input_tokens``；OpenAI 的 ``prompt_tokens`` 本就含
    cached_tokens。未命中输入 = ``input_tokens - cache_read_tokens``。

    Attributes:
        input_tokens: 输入 token 数（总输入，含缓存部分）
        output_tokens: 输出 token 数
        total_tokens: 总 token 数
        cache_read_tokens: 缓存命中读 token 数（厂商未上报时为 0）
        cache_write_tokens: 缓存写入 token 数（厂商未上报时为 0）
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenUsage:
        return cls(
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            cache_write_tokens=data.get("cache_write_tokens", 0),
        )
