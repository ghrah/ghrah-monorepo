# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``subject plugin verify`` CLI 测试（进程内 main()，零 Subject runtime）。

S0 验收标志③：--all 模式无 Subject 进程检出 capability 闭环失败。
"""

from __future__ import annotations

from typing import Any

import pytest
from ghrah.plugin.spec import PluginSpec

from ghrah.subject.cli import main


def _spec(
    plugin_id: str,
    *,
    capabilities: list[str] | None = None,
    requires_caps: list[str] | None = None,
    prefix: str | None = None,
) -> PluginSpec:
    return PluginSpec(
        plugin_id=plugin_id,
        version="1.0.0",
        prefix=prefix,
        provides={"capabilities": capabilities or []},
        requires={"capabilities": requires_caps or []},
    )


def _patch_discovery(monkeypatch: Any, specs: list[PluginSpec]) -> None:
    from ghrah.plugin.loader import DiscoveredPlugin

    discovered = [DiscoveredPlugin(spec=spec, entry_point_name=spec.plugin_id) for spec in specs]

    def _fake_discover(group: str = "ghrah.plugins") -> tuple[list[Any], list[Any]]:
        return discovered, []

    monkeypatch.setattr("ghrah.subject.cli.discover_plugins", _fake_discover)


def _patch_core_version(monkeypatch: Any, core_version: str | None) -> None:
    monkeypatch.setattr("ghrah.subject.cli._core_version", lambda: core_version)


@pytest.fixture()
def _no_env(monkeypatch: Any) -> None:
    monkeypatch.delenv("GHRAH_SUBJECT_PLUGIN_TRUST", raising=False)


def test_all_mode_capability_closure_failure_detected(
    capsys: pytest.CaptureFixture[str], monkeypatch: Any, _no_env: None
) -> None:
    _patch_discovery(
        monkeypatch,
        [
            _spec("consumer", requires_caps=["demo:missing"]),
            _spec("provider", capabilities=["demo:x"], prefix="demo:"),
        ],
    )
    _patch_core_version(monkeypatch, "0.2.0")
    code = main(["plugin", "verify", "--all"])
    assert code == 1
    out = capsys.readouterr().out
    assert "capability closure failed" in out
    assert "demo:missing" in out


def test_all_mode_green(
    capsys: pytest.CaptureFixture[str], monkeypatch: Any, _no_env: None
) -> None:
    _patch_discovery(
        monkeypatch,
        [
            _spec("provider", capabilities=["demo:x"], prefix="demo:"),
            _spec("consumer", requires_caps=["demo:x"]),
        ],
    )
    _patch_core_version(monkeypatch, "0.2.0")
    assert main(["plugin", "verify", "--all"]) == 0
    out = capsys.readouterr().out
    assert "0 error(s)" in out


def test_empty_environment_smoke(
    capsys: pytest.CaptureFixture[str], monkeypatch: Any, _no_env: None
) -> None:
    _patch_discovery(monkeypatch, [])
    _patch_core_version(monkeypatch, "0.2.0")
    assert main(["plugin", "verify", "--all"]) == 0
    assert "no plugins discovered" in capsys.readouterr().out


def test_trust_filter_selects_discovered(
    capsys: pytest.CaptureFixture[str], monkeypatch: Any, _no_env: None
) -> None:
    _patch_discovery(
        monkeypatch,
        [
            _spec("trusted-plugin", capabilities=["demo:x"], prefix="demo:"),
            _spec("untrusted-plugin", requires_caps=["demo:missing"]),
        ],
    )
    _patch_core_version(monkeypatch, "0.2.0")
    monkeypatch.setenv("GHRAH_SUBJECT_PLUGIN_TRUST", "trusted-plugin")
    # 只验证 trusted；untrusted 的 requires 不进闭环 → 绿
    assert main(["plugin", "verify"]) == 0
    out = capsys.readouterr().out
    assert "1 plugin(s)" in out
    assert "0 error(s)" in out


def test_trusted_ghost_not_discovered(
    capsys: pytest.CaptureFixture[str], monkeypatch: Any, _no_env: None
) -> None:
    _patch_discovery(monkeypatch, [])
    _patch_core_version(monkeypatch, "0.2.0")
    monkeypatch.setenv("GHRAH_SUBJECT_PLUGIN_TRUST", "ghost-plugin")
    code = main(["plugin", "verify"])
    assert code == 1
    out = capsys.readouterr().out
    assert "ghost-plugin" in out
    assert "not discovered" in out


def test_empty_trust_hint(
    capsys: pytest.CaptureFixture[str], monkeypatch: Any, _no_env: None
) -> None:
    _patch_discovery(monkeypatch, [_spec("some-plugin")])
    _patch_core_version(monkeypatch, "0.2.0")
    assert main(["plugin", "verify"]) == 0
    assert "trust list is empty" in capsys.readouterr().out


def test_candidate_provides_enrichment_in_trusted_mode(
    capsys: pytest.CaptureFixture[str], monkeypatch: Any, _no_env: None
) -> None:
    # A3 探针：错误列候选插件（未信任的 provider 能补缺口，verify 提示候选）
    _patch_discovery(
        monkeypatch,
        [
            _spec("consumer", requires_caps=["demo:x"]),
            _spec("untrusted-provider", capabilities=["demo:x"], prefix="demo:"),
        ],
    )
    _patch_core_version(monkeypatch, "0.2.0")
    monkeypatch.setenv("GHRAH_SUBJECT_PLUGIN_TRUST", "consumer")
    code = main(["plugin", "verify"])
    assert code == 1
    out = capsys.readouterr().out
    assert "capability closure failed" in out
    assert "untrusted-provider" in out
