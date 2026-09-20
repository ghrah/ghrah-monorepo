# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""plugin spec：插件声明式契约（SSOT 在本包，A7/A9）。

术语裁决（A7）：叫 **plugin spec**，禁叫 "plugin manifest"（Core 已占用 manifest 词）。
spec 是不可变契约（A14）：由插件包作者提供，用户/发行版不改写；
实例配置（instances drop-in）与 allowlist 是可写策略层，不在本模块。

裁决落位：
- A3：schema 禁依赖语义字段（``extra="forbid"`` 天然拒绝 ``depends_on`` /
  ``requires.plugins`` 等）；``after`` 是排序声明非依赖，显式合法。
- A13：``after`` 仅声明装配顺序，被引用插件缺失不阻塞挂载。
- R1：每扩展点超时预算（``timeout_ms`` / ``on_timeout``）。
- R2：capability 分层命名 ``prefix:name``；``core:`` 前缀由注册表统一注册，
  插件 provides 侧禁止使用；裸字符串无前缀被拒。
- R4：``schema_version`` + 幂等迁移函数链（v1 基线，零迁移函数，机制先行）。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "PluginSpec",
    "ProvidesSpec",
    "RequiresSpec",
    "migrate_spec",
    "plugin_spec_json_schema",
]

SPEC_SCHEMA_VERSION = 1

_PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$")
_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9-]*:$")
_CAPABILITY_PATTERN = re.compile(r"^([a-z][a-z0-9-]*):([a-z0-9][a-z0-9/_-]*)$")
_CORE_PREFIX = "core"


def _parse_capability(value: str) -> tuple[str, str] | None:
    """解析 ``prefix:name`` 形状的 capability，形状非法返回 None。"""

    matched = _CAPABILITY_PATTERN.match(value)
    if matched is None:
        return None
    return matched.group(1), matched.group(2)


class ProvidesSpec(BaseModel):
    """插件对外提供的能力声明。

    Attributes:
        checkers: checker 扩展点名（如 ``commit_in_repo``）。
        evidence_kinds: evidence 种类名（如 ``git_commit``）。
        commands: 命令名。
        capabilities: 通用 capability（``prefix:name`` 分层格式，R2）。
    """

    model_config = ConfigDict(extra="forbid")

    checkers: list[str] = Field(default_factory=list)
    evidence_kinds: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class RequiresSpec(BaseModel):
    """插件对外部环境的依赖声明（不含插件间依赖，A3）。

    Attributes:
        core_version: ghrah-core 版本约束（PEP 440 specifier）。
        capabilities: 需要的 capability 清单（可来自其他插件或注册表 core:）。
        host_capability: 宿主能力清单（如 TS 半的 ``node-assembler``）。
    """

    model_config = ConfigDict(extra="forbid")

    core_version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    host_capability: list[str] = Field(default_factory=list)

    @field_validator("core_version")
    @classmethod
    def _validate_core_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from packaging.specifiers import InvalidSpecifier, SpecifierSet

        try:
            SpecifierSet(value)
        except InvalidSpecifier as exc:
            raise ValueError(f"core_version is not a valid PEP 440 specifier: {value!r}") from exc
        return value


class PluginSpec(BaseModel):
    """plugin spec：插件声明式契约（不可变，A14）。

    Attributes:
        schema_version: spec schema 版本（R4 迁移链锚点）。
        plugin_id: 插件身份标识（kebab-case）。
        version: 插件版本（三段数字核心；协商时仅做相等比较，D6）。
        prefix: 自定义 capability 命名空间（如 ``"jira:"``；缺省用 plugin_id）。
        provides: 对外提供的能力声明。
        requires: 对外部环境的依赖声明。
        multi_instance: 是否允许多实例装配。
        timeout_ms: 扩展点超时预算（R1，默认 5s）。
        on_timeout: 超时裁决策略（R1，默认 reject）。
        after: 装配顺序声明（A13；排序声明非依赖，A3 显式豁免）。
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SPEC_SCHEMA_VERSION
    plugin_id: str
    version: str
    prefix: str | None = None
    provides: ProvidesSpec = Field(default_factory=ProvidesSpec)
    requires: RequiresSpec = Field(default_factory=RequiresSpec)
    multi_instance: bool = False
    timeout_ms: int = Field(default=5000, ge=1)
    on_timeout: str = Field(default="reject")
    after: list[str] = Field(default_factory=list)

    @field_validator("plugin_id")
    @classmethod
    def _validate_plugin_id(cls, value: str) -> str:
        if not _PLUGIN_ID_PATTERN.match(value):
            raise ValueError(
                f"plugin_id must be kebab-case (lowercase alphanumeric + hyphen): {value!r}"
            )
        return value

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if not _VERSION_PATTERN.match(value):
            raise ValueError(
                f"version must be numeric core with optional pre/build suffix: {value!r}"
            )
        return value

    @field_validator("prefix")
    @classmethod
    def _validate_prefix(cls, value: str | None) -> str | None:
        if value is not None and not _PREFIX_PATTERN.match(value):
            raise ValueError(
                f"prefix must look like 'jira:' (lowercase + trailing colon): {value!r}"
            )
        return value

    @field_validator("on_timeout")
    @classmethod
    def _validate_on_timeout(cls, value: str) -> str:
        if value not in ("reject", "allow_with_warn"):
            raise ValueError(f"on_timeout must be 'reject' or 'allow_with_warn': {value!r}")
        return value

    @field_validator("after")
    @classmethod
    def _validate_after(cls, value: list[str]) -> list[str]:
        for referenced in value:
            if not _PLUGIN_ID_PATTERN.match(referenced):
                raise ValueError(f"after entries must be plugin_id (kebab-case): {referenced!r}")
        return value

    @field_validator("provides")
    @classmethod
    def _validate_provides_capabilities(cls, value: ProvidesSpec) -> ProvidesSpec:
        for capability in value.capabilities:
            if _parse_capability(capability) is None:
                raise ValueError(
                    f"provides.capabilities entries must be 'prefix:name' (R2): {capability!r}"
                )
        return value

    @model_validator(mode="after")
    def _validate_capability_namespaces(self) -> PluginSpec:
        declared = (self.prefix or f"{self.plugin_id}:").removesuffix(":")
        for capability in self.provides.capabilities:
            parsed = _parse_capability(capability)
            assert parsed is not None  # 形状已在 field_validator 校验
            namespace, _ = parsed
            if namespace == _CORE_PREFIX:
                raise ValueError(
                    f"provides.capabilities must not use reserved 'core:' prefix: {capability!r}"
                )
            if namespace != declared:
                raise ValueError(
                    f"provides.capabilities namespace {namespace!r} does not match "
                    f"declared prefix {declared!r} (R2)"
                )
        for capability in self.requires.capabilities:
            if _parse_capability(capability) is None:
                raise ValueError(
                    f"requires.capabilities entries must be 'prefix:name' (R2): {capability!r}"
                )
        return self


# MIGRATIONS：schema_version → 迁移函数链（R4）。
# v1 是基线版本，无历史版本需要迁移；未来 bump SPEC_SCHEMA_VERSION 时
# 在此登记 ``n -> n+1`` 的幂等迁移函数（输入/输出均为原始 dict）。
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def migrate_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """按当前 schema 版本迁移原始 spec dict（R4，幂等）。

    规则：
    - ``schema_version`` 缺失 → 视为当前版（有默认值的字段由 pydantic 静默补齐）；
    - 低于当前版 → 依次应用 MIGRATIONS 迁移链；
    - 等于当前版 → 原样返回（浅拷贝）；
    - 大于当前版 → 拒载（ValueError），提示升级 ghrah-plugin。

    Raises:
        ValueError: 版本不可迁移或迁移链缺口。
    """

    data = dict(raw)
    declared = data.get("schema_version", SPEC_SCHEMA_VERSION)
    if not isinstance(declared, int):
        raise ValueError(f"schema_version must be an int, got {declared!r}")
    if declared > SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"plugin spec schema_version {declared} is newer than supported "
            f"{SPEC_SCHEMA_VERSION}; upgrade ghrah-plugin"
        )
    while declared < SPEC_SCHEMA_VERSION:
        step = MIGRATIONS.get(declared)
        if step is None:
            raise ValueError(
                f"no migration registered from schema_version {declared} "
                f"to {declared + 1}; upgrade ghrah-plugin"
            )
        data = step(data)
        declared += 1
    data["schema_version"] = SPEC_SCHEMA_VERSION
    return data


def plugin_spec_json_schema() -> dict[str, Any]:
    """生成 plugin spec 的 JSON Schema（S1/S4 TS 侧生成消费）。"""

    return PluginSpec.model_json_schema()
