# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""协商纯函数测试（S0 验收标志②：三种错位响应正确）。"""

from __future__ import annotations

from ghrah.plugin.negotiator import (
    PythonHalfInfo,
    TsHalfReport,
    negotiate,
    python_half_from_spec,
)
from ghrah.plugin.spec import PluginSpec


def _py(plugin_id: str, version: str = "1.0.0", **kwargs: object) -> PythonHalfInfo:
    return PythonHalfInfo(plugin_id=plugin_id, version=version, **kwargs)  # type: ignore[arg-type]


def _ts(plugin_id: str, version: str = "1.0.0", **kwargs: object) -> TsHalfReport:
    return TsHalfReport(plugin_id=plugin_id, version=version, **kwargs)  # type: ignore[arg-type]


def test_matched_full_fields() -> None:
    python = [_py("demo", provides=["checker/x", "command/y"], requires_capabilities=["core:z"])]
    ts = [_ts("demo", provides=["badge/z"])]
    result = negotiate(python, ts)
    assert len(result.matched) == 1
    matched = result.matched[0]
    assert matched.plugin_id == "demo"
    assert matched.version == "1.0.0"
    # provides 并集且保序去重
    assert matched.provides == ["checker/x", "command/y", "badge/z"]
    assert result.python_only == []
    assert result.ts_only == []
    assert result.version_conflicts == []
    assert result.instances == {"demo": []}


def test_python_only_misalignment() -> None:
    result = negotiate([_py("py-only")], [])
    assert [p.plugin_id for p in result.python_only] == ["py-only"]
    assert result.matched == []


def test_ts_only_misalignment() -> None:
    result = negotiate([], [_ts("ts-only")])
    assert [t.plugin_id for t in result.ts_only] == ["ts-only"]
    assert result.matched == []


def test_version_conflict_detected() -> None:
    result = negotiate([_py("demo", version="1.0.0")], [_ts("demo", version="2.0.0")])
    assert result.matched == []
    assert len(result.version_conflicts) == 1
    conflict = result.version_conflicts[0]
    assert conflict.plugin_id == "demo"
    assert conflict.python_version == "1.0.0"
    assert conflict.ts_version == "2.0.0"


def test_capability_missing_linkage() -> None:
    python = [
        _py("consumer", requires_capabilities=["core:checker/missing"]),
        _py("provider", provides=["core:checker/other"]),
    ]
    result = negotiate(python, [])
    assert result.missing_capabilities == ["core:checker/missing"]


def test_capability_closure_satisfied_by_ts_half() -> None:
    python = [_py("consumer", requires_capabilities=["badge:x"])]
    ts = [_ts("provider", provides=["badge:x"])]
    result = negotiate(python, ts)
    # provider 仅 TS 侧在场（ts_only），但 capability 闭环以双侧 provides 计算
    assert result.missing_capabilities == []
    assert [t.plugin_id for t in result.ts_only] == ["provider"]


def test_instances_passthrough() -> None:
    python = [_py("demo", instances=["prod-eu", "staging"])]
    result = negotiate(python, [_ts("demo")])
    assert result.matched[0].instances == ["prod-eu", "staging"]
    assert result.instances["demo"] == ["prod-eu", "staging"]


def test_python_half_from_spec_flattens_provides() -> None:
    spec = PluginSpec(
        plugin_id="demo",
        version="1.2.3",
        prefix="demo:",
        provides={
            "checkers": ["commit_in_repo"],
            "evidence_kinds": ["git_commit"],
            "commands": ["demo_run"],
            "capabilities": ["demo:attr/x"],
        },
        requires={"capabilities": ["core:checker/y"]},
    )
    info = python_half_from_spec(spec, instances=["prod"])
    assert info.plugin_id == "demo"
    assert info.version == "1.2.3"
    assert info.provides == [
        "checker/commit_in_repo",
        "evidence-kind/git_commit",
        "command/demo_run",
        "demo:attr/x",
    ]
    assert info.requires_capabilities == ["core:checker/y"]
    assert info.instances == ["prod"]


def test_empty_inputs() -> None:
    result = negotiate([], [])
    assert result.matched == []
    assert result.missing_capabilities == []
    assert result.instances == {}
