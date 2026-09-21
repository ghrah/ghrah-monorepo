# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""checkers 测试：注册/注销/resolve、冻结不可变（A16）、非法返回归一。"""

from __future__ import annotations

from typing import Any

import pytest

from ghrah.taskstore.checkers import (
    CheckerRegistry,
    CheckOutcome,
    freeze_mapping,
    normalize_result,
    run_checker,
)


def _always_pass(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
    return {"passed": True, "detail": None}


def _mutating_checker(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
    evidence["kind"] = "tampered"  # type: ignore[index]
    return {"passed": True}


class TestRegistry:
    def test_register_resolve_unregister(self):
        registry = CheckerRegistry()
        assert registry.resolve("commit_in_repo") is None
        registry.register("commit_in_repo", _always_pass)
        assert registry.resolve("commit_in_repo") is _always_pass
        assert registry.candidates() == ["commit_in_repo"]
        assert registry.unregister("commit_in_repo") is True
        assert registry.unregister("commit_in_repo") is False
        assert registry.resolve("commit_in_repo") is None

    def test_register_overwrite_last_wins(self):
        def other(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
            return {"passed": False}

        registry = CheckerRegistry()
        registry.register("x", _always_pass)
        registry.register("x", other)
        assert registry.resolve("x") is other


class TestFreeze:
    def test_frozen_mapping_rejects_mutation(self):
        frozen = freeze_mapping({"kind": "git_commit", "payload": {"sha": "abc"}, "list": [1, 2]})
        with pytest.raises(TypeError):
            frozen["kind"] = "tampered"  # type: ignore[index]
        with pytest.raises(TypeError):
            frozen["payload"]["sha"] = "tampered"  # type: ignore[index]

    def test_run_checker_mutating_input_raises_inside_and_fails(self):
        """A16 探针：checker 尝试修改入参 → TypeError → 归一为失败，宿主未被污染。"""
        evidence = {"kind": "git_commit"}
        task = {"title": "demo"}
        outcome = run_checker(_mutating_checker, "bad", evidence=evidence, task=task)
        assert outcome.passed is False
        assert outcome.detail is not None and "checker error" in outcome.detail
        assert evidence["kind"] == "git_commit"  # 宿主数据未被污染
        assert task["title"] == "demo"


class TestNormalize:
    def test_valid_result(self):
        outcome = normalize_result("x", {"passed": True, "detail": "ok"})
        assert outcome == CheckOutcome(checker="x", passed=True, detail="ok")

    def test_missing_passed(self):
        outcome = normalize_result("x", {"detail": "no passed key"})
        assert outcome.passed is False
        assert outcome.detail == "invalid checker result"

    def test_wrong_type_passed(self):
        outcome = normalize_result("x", {"passed": "yes"})
        assert outcome.passed is False
        assert outcome.detail == "invalid checker result"

    def test_non_mapping_result(self):
        def bad_checker(evidence: Any, task: Any, config: Any) -> str:
            return "not a mapping"

        outcome = run_checker(bad_checker, "x", evidence={}, task={})
        assert outcome.passed is False
        assert "checker error" in (outcome.detail or "")

    def test_raising_checker_normalized(self):
        def boom(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
            raise RuntimeError("plugin bug")

        outcome = run_checker(boom, "x", evidence={}, task={})
        assert outcome.passed is False
        assert "plugin bug" in (outcome.detail or "")

    def test_outcome_frozen(self):
        outcome = CheckOutcome(checker="x", passed=True)
        with pytest.raises(Exception):
            outcome.passed = False  # type: ignore[misc]
