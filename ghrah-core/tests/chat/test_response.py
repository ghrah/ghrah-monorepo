# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from ghrah.chat.content import ReasoningBlock, TextBlock
from ghrah.chat.format import LLMResponse, TokenUsage
from ghrah.chat.response import (
    extract_reasoning_content,
    extract_response_metadata,
    extract_token_usage,
)


class TestExtractTokenUsage:
    def test_with_token_usage(self) -> None:
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        )
        result = extract_token_usage(resp)
        assert result is not None
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.total_tokens == 150

    def test_all_zero_returns_none(self) -> None:
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            token_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        )
        assert extract_token_usage(resp) is None

    def test_no_token_usage_fallback_to_response_metadata(self) -> None:
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 200,
                    "completion_tokens": 80,
                    "total_tokens": 280,
                },
            },
        )
        result = extract_token_usage(resp)
        assert result is not None
        assert result.input_tokens == 200
        assert result.output_tokens == 80
        assert result.total_tokens == 280

    def test_fallback_reads_usage_key(self) -> None:
        """厂商把用量写在 metadata "usage" key 时同样可提取。"""
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata={
                "usage": {
                    "prompt_tokens": 300,
                    "completion_tokens": 120,
                    "total_tokens": 420,
                },
            },
        )
        result = extract_token_usage(resp)
        assert result is not None
        assert result.input_tokens == 300
        assert result.output_tokens == 120
        assert result.total_tokens == 420

    def test_token_usage_key_preferred_over_usage_key(self) -> None:
        """两 key 并存时 "token_usage" 优先。"""
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
                "usage": {
                    "prompt_tokens": 999,
                    "completion_tokens": 999,
                    "total_tokens": 999,
                },
            },
        )
        result = extract_token_usage(resp)
        assert result is not None
        assert result.input_tokens == 10
        assert result.total_tokens == 15

    def test_no_metadata_returns_none(self) -> None:
        resp = LLMResponse(content_blocks=[TextBlock(text="Hello")])
        assert extract_token_usage(resp) is None

    def test_fallback_reads_anthropic_style_keys(self) -> None:
        """Anthropic 风格键名（input_tokens/output_tokens）同样可提取。"""
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata={
                "usage": {
                    "input_tokens": 300,
                    "output_tokens": 120,
                },
            },
        )
        result = extract_token_usage(resp)
        assert result is not None
        assert result.input_tokens == 300
        assert result.output_tokens == 120

    def test_fallback_reads_cache_keys(self) -> None:
        """cache 键双风格兼容（cached_tokens / cache_read_input_tokens）。"""
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata={
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 50,
                    "cached_tokens": 768,
                },
            },
        )
        result = extract_token_usage(resp)
        assert result is not None
        assert result.cache_read_tokens == 768

        resp2 = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata={
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 2000,
                    "cache_creation_input_tokens": 300,
                },
            },
        )
        result2 = extract_token_usage(resp2)
        assert result2 is not None
        assert result2.cache_read_tokens == 2000
        assert result2.cache_write_tokens == 300

    def test_rejects_non_llmresponse(self) -> None:
        with pytest.raises(TypeError, match="Expected LLMResponse"):
            extract_token_usage("not a response")  # type: ignore[arg-type]


class TestExtractReasoningContent:
    def test_with_reasoning(self) -> None:
        resp = LLMResponse(
            content_blocks=[ReasoningBlock(reasoning="thinking..."), TextBlock(text="answer")],
        )
        assert extract_reasoning_content(resp) == "thinking..."

    def test_no_reasoning_returns_none(self) -> None:
        resp = LLMResponse(content_blocks=[TextBlock(text="answer")])
        assert extract_reasoning_content(resp) is None

    def test_empty_reasoning_returns_none(self) -> None:
        resp = LLMResponse(content_blocks=[ReasoningBlock(reasoning=""), TextBlock(text="answer")])
        assert extract_reasoning_content(resp) is None

    def test_empty_content_blocks_returns_none(self) -> None:
        resp = LLMResponse(content_blocks=[])
        assert extract_reasoning_content(resp) is None

    def test_rejects_non_llmresponse(self) -> None:
        with pytest.raises(TypeError, match="Expected LLMResponse"):
            extract_reasoning_content(42)  # type: ignore[arg-type]


class TestExtractResponseMetadata:
    def test_with_metadata(self) -> None:
        meta = {"model": "gpt-4", "finish_reason": "stop"}
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata=meta,
        )
        result = extract_response_metadata(resp)
        assert result == meta

    def test_returns_copy(self) -> None:
        meta = {"model": "gpt-4"}
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata=meta,
        )
        result = extract_response_metadata(resp)
        result["extra"] = "value"
        assert "extra" not in meta

    def test_empty_metadata_returns_empty(self) -> None:
        resp = LLMResponse(
            content_blocks=[TextBlock(text="Hello")],
            response_metadata={},
        )
        assert extract_response_metadata(resp) == {}

    def test_no_metadata_returns_empty(self) -> None:
        resp = LLMResponse(content_blocks=[TextBlock(text="Hello")])
        assert extract_response_metadata(resp) == {}

    def test_rejects_non_llmresponse(self) -> None:
        with pytest.raises(TypeError, match="Expected LLMResponse"):
            extract_response_metadata({"key": "val"})  # type: ignore[arg-type]
