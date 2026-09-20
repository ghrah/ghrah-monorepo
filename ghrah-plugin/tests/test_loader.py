# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件发现测试（D1 entry_point 导入式；发现 ≠ 启用）。

entry point value 是 ``module:attr`` 字符串，经真实 import 机制加载
（测试目标模块：tests/loader_targets.py）。
"""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

from ghrah.plugin.loader import discover_plugins

_TARGETS_MODULE = "loader_targets"


def _ep(name: str, attr: str) -> EntryPoint:
    return EntryPoint(name=name, value=f"{_TARGETS_MODULE}:{attr}", group="ghrah.plugins")


class _FakeEntryPoints:
    def __init__(self, entries: list[EntryPoint]) -> None:
        self._entries = entries

    def select(self, group: str) -> list[EntryPoint]:
        assert group == "ghrah.plugins"
        return self._entries


def _patch(monkeypatch: Any, entries: list[EntryPoint]) -> None:
    monkeypatch.setattr("ghrah.plugin.loader.entry_points", lambda: _FakeEntryPoints(entries))


def test_normal_discovery_instance_and_factory(monkeypatch: Any) -> None:
    _patch(monkeypatch, [_ep("plugin-a", "spec_a"), _ep("plugin-b", "factory_b")])
    discovered, issues = discover_plugins()
    assert [d.spec.plugin_id for d in discovered] == ["plugin-a", "plugin-b"]
    assert discovered[0].entry_point_name == "plugin-a"
    assert issues == []


def test_non_spec_target_becomes_issue(monkeypatch: Any) -> None:
    _patch(monkeypatch, [_ep("bad", "not_a_spec")])
    discovered, issues = discover_plugins()
    assert discovered == []
    assert len(issues) == 1
    assert "not a PluginSpec" in issues[0].error


def test_load_exception_becomes_issue(monkeypatch: Any) -> None:
    _patch(monkeypatch, [_ep("exploder", "explode")])
    discovered, issues = discover_plugins()
    assert discovered == []
    assert len(issues) == 1
    assert "boom" in issues[0].error


def test_duplicate_plugin_id_becomes_issue(monkeypatch: Any) -> None:
    _patch(monkeypatch, [_ep("first", "spec_a"), _ep("second", "spec_dup_a")])
    discovered, issues = discover_plugins()
    assert [d.spec.plugin_id for d in discovered] == ["plugin-a"]
    assert len(issues) == 1
    assert "duplicate plugin_id" in issues[0].error
    assert "first" in issues[0].error


def test_empty_group_returns_empty(monkeypatch: Any) -> None:
    _patch(monkeypatch, [])
    discovered, issues = discover_plugins()
    assert discovered == []
    assert issues == []


def test_dist_name_captured_when_available(monkeypatch: Any) -> None:
    ep = _ep("plugin-a", "spec_a")

    class _Dist:
        name = "some-distribution"

    class _WithDist:
        value = ep.value

        @property
        def name(self) -> str:
            return ep.name

        @property
        def dist(self) -> _Dist:
            return _Dist()

        def load(self) -> Any:
            from ghrah.plugin.spec import PluginSpec

            return PluginSpec(plugin_id="plugin-a", version="1.0.0")

    monkeypatch.setattr("ghrah.plugin.loader.entry_points", lambda: _FakeEntryPoints([_WithDist()]))
    discovered, _ = discover_plugins()
    assert discovered[0].dist_name == "some-distribution"
