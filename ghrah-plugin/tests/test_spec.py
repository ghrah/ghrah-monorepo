# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""PluginSpec 校验测试（R1/R2/R4/A3/A13）。"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ghrah.plugin.spec import (
    SPEC_SCHEMA_VERSION,
    PluginSpec,
    migrate_spec,
    plugin_spec_json_schema,
)


def _raw_spec(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"plugin_id": "demo-plugin", "version": "1.0.0"}
    base.update(overrides)
    return base


def test_minimal_spec_is_valid() -> None:
    spec = PluginSpec.model_validate(_raw_spec())
    assert spec.plugin_id == "demo-plugin"
    assert spec.schema_version == SPEC_SCHEMA_VERSION
    assert spec.multi_instance is False


def test_defaults_r1() -> None:
    spec = PluginSpec.model_validate(_raw_spec())
    assert spec.timeout_ms == 5000
    assert spec.on_timeout == "reject"


def test_full_spec_roundtrip() -> None:
    raw = _raw_spec(
        prefix="demo:",
        provides={
            "checkers": ["commit_in_repo"],
            "evidence_kinds": ["git_commit"],
            "commands": ["demo_run"],
            "capabilities": ["demo:attr/x"],
        },
        requires={"core_version": ">=0.2.0", "capabilities": ["core:checker/y"]},
        multi_instance=True,
        timeout_ms=1000,
        on_timeout="allow_with_warn",
        after=["other-plugin"],
    )
    spec = PluginSpec.model_validate(raw)
    assert spec.provides.capabilities == ["demo:attr/x"]
    assert spec.requires.capabilities == ["core:checker/y"]
    dumped = spec.model_dump()
    assert PluginSpec.model_validate(dumped) == spec


# ── R2：capability 分层命名 ──


def test_bare_capability_rejected() -> None:
    with pytest.raises(ValidationError, match="prefix:name"):
        PluginSpec.model_validate(_raw_spec(provides={"capabilities": ["bare-name"]}))


def test_core_prefix_provides_rejected() -> None:
    with pytest.raises(ValidationError, match="core:"):
        PluginSpec.model_validate(
            _raw_spec(prefix="core:", provides={"capabilities": ["core:evidence-kind/z"]})
        )


def test_core_prefix_requires_allowed() -> None:
    spec = PluginSpec.model_validate(
        _raw_spec(requires={"capabilities": ["core:checker/commit_in_repo"]})
    )
    assert spec.requires.capabilities == ["core:checker/commit_in_repo"]


def test_wrong_namespace_rejected() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        PluginSpec.model_validate(_raw_spec(provides={"capabilities": ["other:attr/x"]}))


def test_declared_prefix_namespace_accepted() -> None:
    spec = PluginSpec.model_validate(
        _raw_spec(prefix="demo:", provides={"capabilities": ["demo:attr/x"]})
    )
    assert spec.provides.capabilities == ["demo:attr/x"]


# ── A3：禁依赖语义字段，after 显式豁免 ──


def test_dependency_semantics_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        PluginSpec.model_validate(_raw_spec(depends_on=["other"]))
    with pytest.raises(ValidationError):
        PluginSpec.model_validate(_raw_spec(requires={"plugins": ["other"]}))


def test_after_is_not_dependency_field() -> None:
    spec = PluginSpec.model_validate(_raw_spec(after=["other-plugin"]))
    assert spec.after == ["other-plugin"]


# ── 形状校验 ──


@pytest.mark.parametrize(
    "plugin_id",
    ["Demo", "demo_", "-demo", "demo plugin", ""],
)
def test_bad_plugin_id_rejected(plugin_id: str) -> None:
    with pytest.raises(ValidationError):
        PluginSpec.model_validate(_raw_spec(plugin_id=plugin_id))


@pytest.mark.parametrize(
    "version",
    ["1.0", "v1.0.0", "1.x.0", "latest"],
)
def test_bad_version_rejected(version: str) -> None:
    with pytest.raises(ValidationError):
        PluginSpec.model_validate(_raw_spec(version=version))


def test_bad_prefix_rejected() -> None:
    with pytest.raises(ValidationError):
        PluginSpec.model_validate(_raw_spec(prefix="demo"))


def test_bad_core_version_rejected() -> None:
    with pytest.raises(ValidationError, match="PEP 440"):
        PluginSpec.model_validate(_raw_spec(requires={"core_version": "not-a-spec"}))


def test_bad_on_timeout_rejected() -> None:
    with pytest.raises(ValidationError):
        PluginSpec.model_validate(_raw_spec(on_timeout="ignore"))


# ── R4：迁移链 ──


def test_migrate_missing_version_treated_as_current() -> None:
    raw = _raw_spec()
    migrated = migrate_spec(raw)
    assert migrated["schema_version"] == SPEC_SCHEMA_VERSION
    # 有默认值的字段静默补齐
    spec = PluginSpec.model_validate(migrated)
    assert spec.timeout_ms == 5000


def test_migrate_current_version_passthrough() -> None:
    raw = _raw_spec(schema_version=SPEC_SCHEMA_VERSION)
    migrated = migrate_spec(raw)
    assert migrated["schema_version"] == SPEC_SCHEMA_VERSION


def test_migrate_future_version_rejected() -> None:
    with pytest.raises(ValueError, match="upgrade ghrah-plugin"):
        migrate_spec(_raw_spec(schema_version=SPEC_SCHEMA_VERSION + 1))


def test_migrate_non_int_version_rejected() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        migrate_spec(_raw_spec(schema_version="1"))


def test_json_schema_generation_smoke() -> None:
    schema = plugin_spec_json_schema()
    assert schema.get("title") == "PluginSpec"
    for key in ("plugin_id", "version", "provides", "requires", "multi_instance", "after"):
        assert key in schema["properties"]
    # extra=forbid 体现在 JSON Schema（A3 的机器可读面）
    assert schema.get("additionalProperties") is False
