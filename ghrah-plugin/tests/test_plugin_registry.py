# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""注册表测试：capability 求解 + after 稳定排序。"""

from __future__ import annotations

import pytest

from ghrah.plugin.errors import CapabilityMissingError
from ghrah.plugin.registry import PluginRegistry, sort_for_mount
from ghrah.plugin.spec import PluginSpec


def _spec(
    plugin_id: str,
    *,
    capabilities: list[str] | None = None,
    commands: list[str] | None = None,
    checkers: list[str] | None = None,
    after: list[str] | None = None,
    prefix: str | None = None,
) -> PluginSpec:
    return PluginSpec(
        plugin_id=plugin_id,
        version="1.0.0",
        prefix=prefix,
        provides={
            "capabilities": capabilities or [],
            "commands": commands or [],
            **({"checkers": checkers} if checkers else {}),
        },
        after=after or [],
    )


# ── capability 求解 ──


def test_resolve_capability_multiple_providers() -> None:
    registry = PluginRegistry(
        [
            _spec("alpha", capabilities=["alpha:attr/x"]),
            _spec("beta", capabilities=["alpha:attr/x", "alpha:attr/y"], prefix="alpha:"),
        ]
    )
    assert registry.resolve_capability("alpha:attr/x") == ["alpha", "beta"]
    assert registry.resolve_capability("alpha:attr/y") == ["beta"]


def test_resolve_capability_miss_returns_empty() -> None:
    registry = PluginRegistry([_spec("alpha", capabilities=["alpha:attr/x"])])
    assert registry.resolve_capability("core:checker/none") == []


def test_capability_missing_error_carries_candidates() -> None:
    registry = PluginRegistry([_spec("alpha", capabilities=["alpha:attr/x"])])
    missing = ["core:checker/none"]
    candidates = {capability: registry.resolve_capability(capability) for capability in missing}
    error = CapabilityMissingError(missing, candidates)
    assert error.missing == missing
    assert error.candidates["core:checker/none"] == []
    assert "core:checker/none" in str(error)


def test_check_provides_hit_and_miss() -> None:
    registry = PluginRegistry([_spec("alpha", commands=["demo_run"])])
    assert registry.check_provides("demo_run", ["alpha"]) is True
    assert registry.check_provides("other_cmd", ["alpha"]) is False
    assert registry.check_provides("demo_run", ["ghost"]) is False


def test_specs_snapshot_readonly() -> None:
    registry = PluginRegistry([_spec("alpha")])
    snapshot = registry.specs
    snapshot["injected"] = _spec("injected")  # type: ignore[index]
    assert "injected" not in registry.specs


# ── after 稳定排序 ──


def test_sort_respects_after_declaration() -> None:
    first = _spec("first")
    second = _spec("second", after=["first"])
    result = sort_for_mount([second, first])
    assert [s.plugin_id for s in result] == ["first", "second"]


def test_sort_missing_reference_falls_back_to_list_order() -> None:
    # 豁免：被引用插件缺失不阻塞，声明退化为无效果
    orphan = _spec("orphan", after=["ghost"])
    other = _spec("other")
    result = sort_for_mount([orphan, other])
    assert [s.plugin_id for s in result] == ["orphan", "other"]


def test_sort_no_after_preserves_input_order() -> None:
    a, b, c = _spec("c"), _spec("a"), _spec("b")
    result = sort_for_mount([a, b, c])
    assert [s.plugin_id for s in result] == ["c", "a", "b"]


def test_sort_chain_and_stability() -> None:
    base = _spec("base")
    middle = _spec("middle", after=["base"])
    top = _spec("top", after=["middle"])
    free = _spec("free")
    result = sort_for_mount([free, top, middle, base])
    assert [s.plugin_id for s in result] == ["free", "base", "middle", "top"]


def test_sort_cycle_falls_back_gracefully() -> None:
    a = _spec("a", after=["b"])
    b = _spec("b", after=["a"])
    result = sort_for_mount([a, b])
    assert [s.plugin_id for s in result] == ["a", "b"]
    assert len(result) == 2


def test_sort_self_reference_ignored() -> None:
    narcissist = _spec("self-ref", after=["self-ref"])
    result = sort_for_mount([narcissist])
    assert [s.plugin_id for s in result] == ["self-ref"]


def test_sort_empty() -> None:
    assert sort_for_mount([]) == []


def test_sort_after_affects_only_declared() -> None:
    x = _spec("x")
    y = _spec("y", after=["x"])
    z = _spec("z")
    result = sort_for_mount([y, z, x])
    # 无约束的 z 保持相对位置（稳定），x 因 y 的 after 前移
    assert [s.plugin_id for s in result] == ["z", "x", "y"]


@pytest.mark.parametrize(
    ("order", "expected"),
    [
        (["second", "first"], ["first", "second"]),
        (["first", "second"], ["first", "second"]),
    ],
)
def test_sort_result_deterministic(order: list[str], expected: list[str]) -> None:
    specs = {
        "first": _spec("first"),
        "second": _spec("second", after=["first"]),
    }
    result = sort_for_mount([specs[name] for name in order])
    assert [s.plugin_id for s in result] == expected


# ── checker 派生索引（D5：独立存放，不污染 candidates_snapshot）──


def test_resolve_checker_multiple_providers() -> None:
    registry = PluginRegistry(
        [
            _spec("alpha", checkers=["commit_in_repo"]),
            _spec("beta", checkers=["commit_in_repo", "lint_clean"]),
        ]
    )
    assert registry.resolve_checker("commit_in_repo") == ["alpha", "beta"]
    assert registry.resolve_checker("lint_clean") == ["beta"]


def test_resolve_checker_miss_returns_empty() -> None:
    registry = PluginRegistry([_spec("alpha", capabilities=["alpha:attr/x"])])
    assert registry.resolve_checker("none") == []


def test_checker_index_does_not_pollute_capability_semantics() -> None:
    """D15：checker 命中走 resolve_checker；resolve_capability/core: 键仍恒为空。"""
    registry = PluginRegistry([_spec("alpha", checkers=["commit_in_repo"])])
    assert registry.resolve_capability("core:checker/commit_in_repo") == []
    assert registry.candidates_snapshot() == {}
    assert registry.checker_candidates_snapshot() == {"commit_in_repo": ["alpha"]}


def test_checker_candidates_snapshot_readonly() -> None:
    registry = PluginRegistry([_spec("alpha", checkers=["commit_in_repo"])])
    snapshot = registry.checker_candidates_snapshot()
    snapshot["injected"] = ["ghost"]  # type: ignore[index]
    assert "injected" not in registry.checker_candidates_snapshot()
