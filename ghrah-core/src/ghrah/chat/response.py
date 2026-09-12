# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""LLM 响应元数据提取工具函数。

从 LLMResponse 中提取 token 用量、CoT 思考内容和厂商原始响应元数据。
"""

from __future__ import annotations

from typing import Any

from ghrah.chat.format import LLMResponse
from ghrah.types.tokens import TokenUsage

__all__ = [
    "extract_token_usage",
    "extract_reasoning_content",
    "extract_response_metadata",
]


def extract_token_usage(response: LLMResponse) -> TokenUsage | None:
    if not isinstance(response, LLMResponse):
        raise TypeError(f"Expected LLMResponse, got {type(response).__name__}")

    if response.token_usage is not None:
        tu = response.token_usage
        if tu.input_tokens or tu.output_tokens or tu.total_tokens:
            return tu

    if response.response_metadata and isinstance(response.response_metadata, dict):
        raw_usage: dict[str, Any] | None = None
        for key in ("token_usage", "usage"):
            candidate = response.response_metadata.get(key)
            if isinstance(candidate, dict):
                raw_usage = candidate
                break
        if raw_usage is not None:
            # 双风格键兼容：OpenAI（prompt/completion）与 Anthropic（input/output）；
            # cache 键同理（cached_tokens / cache_read_input_tokens）。
            def _pick(*keys: str) -> int:
                for k in keys:
                    v = raw_usage.get(k)
                    if isinstance(v, int) and v:
                        return v
                return 0

            return TokenUsage(
                input_tokens=_pick("input_tokens", "prompt_tokens"),
                output_tokens=_pick("output_tokens", "completion_tokens"),
                total_tokens=_pick("total_tokens"),
                cache_read_tokens=_pick(
                    "cache_read_tokens", "cache_read_input_tokens", "cached_tokens"
                ),
                cache_write_tokens=_pick("cache_write_tokens", "cache_creation_input_tokens"),
            )

    return None


def extract_reasoning_content(response: LLMResponse) -> str | None:
    if not isinstance(response, LLMResponse):
        raise TypeError(f"Expected LLMResponse, got {type(response).__name__}")
    result = response.reasoning
    if not result:
        return None
    return result


def extract_response_metadata(response: LLMResponse) -> dict[str, Any]:
    """从 LLMResponse 提取厂商原始响应元数据。"""
    if not isinstance(response, LLMResponse):
        raise TypeError(f"Expected LLMResponse, got {type(response).__name__}")

    if response.response_metadata and isinstance(response.response_metadata, dict):
        return dict(response.response_metadata)
    return {}
