# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""PluginAssembly 形状校验测试（三态：multi_instance 缺/多 instances、
未启用却配 instances、合法形状）。"""

from __future__ import annotations

from ghrah.plugin.assembly import (
    PluginAssembly,
    PluginInstanceConfig,
    validate_assembly,
)
from ghrah.plugin.spec import PluginSpec


def _spec(plugin_id: str, *, multi_instance: bool = False) -> PluginSpec:
    return PluginSpec(plugin_id=plugin_id, version="0.1.0", multi_instance=multi_instance)


def test_multi_instance_plugin_requires_instances() -> None:
    spec = _spec("fanout", multi_instance=True)
    assembly = PluginAssembly(enabled=["fanout"])
    errors = validate_assembly(spec, assembly)
    assert len(errors) == 1
    assert "multi_instance plugin 'fanout' requires instance" in errors[0]


def test_single_instance_plugin_must_not_declare_instances() -> None:
    spec = _spec("simple")
    assembly = PluginAssembly(
        enabled=["simple"],
        instances={"simple": {"main": PluginInstanceConfig()}},
    )
    errors = validate_assembly(spec, assembly)
    assert len(errors) == 1
    assert "single-instance plugin 'simple' must not declare instances" in errors[0]


def test_instances_for_not_enabled_plugin_rejected() -> None:
    spec = _spec("declared")
    assembly = PluginAssembly(
        enabled=[],
        instances={"declared": {"main": PluginInstanceConfig()}},
    )
    errors = validate_assembly(spec, assembly)
    assert len(errors) == 1
    assert "not in enabled list" in errors[0]


def test_valid_assemblies_pass() -> None:
    single = _spec("simple")
    assert validate_assembly(single, PluginAssembly(enabled=["simple"])) == []
    assert validate_assembly(single, PluginAssembly(enabled=[])) == []

    multi = _spec("fanout", multi_instance=True)
    ok = PluginAssembly(
        enabled=["fanout"],
        instances={"fanout": {"a": PluginInstanceConfig(), "b": PluginInstanceConfig()}},
    )
    assert validate_assembly(multi, ok) == []


def test_assembly_round_trip_and_extra_forbid() -> None:
    import pytest
    from pydantic import ValidationError

    assembly = PluginAssembly(enabled=["p"], instances={"p": {"i": {"enabled": False}}})
    data = assembly.model_dump()
    restored = PluginAssembly.model_validate(data)
    assert restored == assembly
    assert restored.instances["p"]["i"].enabled is False

    with pytest.raises(ValidationError):
        PluginAssembly.model_validate({"enabled": ["p"], "unknown": 1})
    with pytest.raises(ValidationError):
        PluginInstanceConfig.model_validate({"enabled": True, "extra": "x"})
