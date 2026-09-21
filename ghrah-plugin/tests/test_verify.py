# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""离线验证引擎测试。"""

from __future__ import annotations

from ghrah.plugin.loader import LoadIssue
from ghrah.plugin.spec import PluginSpec
from ghrah.plugin.verify import check_capability_closure, verify_plugins


def _spec(
    plugin_id: str,
    *,
    capabilities: list[str] | None = None,
    requires_caps: list[str] | None = None,
    commands: list[str] | None = None,
    core_version: str | None = None,
    prefix: str | None = None,
) -> PluginSpec:
    return PluginSpec(
        plugin_id=plugin_id,
        version="1.0.0",
        prefix=prefix,
        provides={"capabilities": capabilities or [], "commands": commands or []},
        requires={"capabilities": requires_caps or [], "core_version": core_version},
    )


def test_capability_closure_missing_with_candidates() -> None:
    specs = [
        _spec("consumer", requires_caps=["demo:x", "demo:missing"]),
        _spec("provider", capabilities=["demo:x"], prefix="demo:"),
    ]
    findings = verify_plugins(specs)
    closure = [f for f in findings if f.kind == "capability_missing"]
    assert len(closure) == 1
    finding = closure[0]
    assert finding.severity == "error"
    assert "demo:missing" in finding.message
    assert "none" in finding.message  # 无候选时显式 none


def test_capability_closure_lists_provider_candidates() -> None:
    specs = [
        _spec("consumer", requires_caps=["demo:x"]),
        _spec("provider", capabilities=["demo:x"], prefix="demo:"),
    ]
    findings = verify_plugins(specs)
    # demo:x 已被 provider 提供 → 无 capability_missing
    assert all(f.kind != "capability_missing" for f in findings)


def test_check_capability_closure_pure_function() -> None:
    missing, candidates = check_capability_closure(
        requires=["demo:a", "demo:b"],
        provides=[("p1", "demo:a")],
    )
    assert missing == ["demo:b"]
    assert candidates == {"demo:b": []}


def test_command_conflict_detected() -> None:
    specs = [
        _spec("first", commands=["demo_run"]),
        _spec("second", commands=["demo_run"]),
    ]
    findings = verify_plugins(specs)
    conflicts = [f for f in findings if f.kind == "command_conflict"]
    assert len(conflicts) == 1
    assert conflicts[0].plugin_id == "second"
    assert "first" in conflicts[0].message
    assert "demo_run" in conflicts[0].message


def test_command_same_plugin_no_conflict() -> None:
    specs = [_spec("only", commands=["demo_run", "demo_run"])]
    findings = verify_plugins(specs)
    assert all(f.kind != "command_conflict" for f in findings)


def test_core_version_mismatch_is_error() -> None:
    specs = [_spec("demo", core_version=">=0.3.0")]
    findings = verify_plugins(specs, core_version="0.2.0")
    conflicts = [f for f in findings if f.kind == "version_conflict"]
    assert len(conflicts) == 1
    assert conflicts[0].plugin_id == "demo"
    assert "0.3.0" in conflicts[0].message


def test_core_version_match_no_finding() -> None:
    specs = [_spec("demo", core_version=">=0.1.0")]
    assert verify_plugins(specs, core_version="0.2.0") == []


def test_core_not_installed_is_warning() -> None:
    specs = [_spec("demo", core_version=">=0.1.0")]
    findings = verify_plugins(specs, core_version=None)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "not installed" in findings[0].message


def test_load_issues_become_findings() -> None:
    issues = [LoadIssue(entry_point="broken", error="import exploded")]
    findings = verify_plugins([], load_issues=issues)
    assert len(findings) == 1
    assert findings[0].kind == "load_failed"
    assert findings[0].severity == "error"
    assert "broken" in findings[0].message
    assert "import exploded" in findings[0].message


def test_all_green_returns_empty() -> None:
    specs = [
        _spec("provider", capabilities=["demo:x"], prefix="demo:"),
        _spec("consumer", requires_caps=["demo:x"]),
    ]
    assert verify_plugins(specs, core_version="1.0.0") == []


def test_candidate_provides_enriches_missing_detail() -> None:
    # 错误列候选插件（发现但未信任的 provider 提供缺失 capability）
    specs = [_spec("consumer", requires_caps=["demo:x"])]
    findings = verify_plugins(
        specs,
        candidate_provides=[("untrusted-provider", "demo:x")],
    )
    closure = [f for f in findings if f.kind == "capability_missing"]
    assert len(closure) == 1
    assert "untrusted-provider" in closure[0].message
