# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件装配模型（Project 侧装配事实的权威形状，SSOT 在本包）。

``PluginAssembly`` 是 Project 侧装配事实的权威载体（``ProjectRecord.config.
plugins``）：enabled 清单同时是装配顺序；instances 是 multi_instance 插件的
drop-in 实例配置（spec 只读，instances 可写）。序列化形态由 pydantic
round-trip 持久化（ProjectStore 内 ProjectRecord 字段），不新增 TOML 面。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ghrah.plugin.spec import PluginSpec

__all__ = [
    "PluginAssembly",
    "PluginInstanceConfig",
    "validate_assembly",
]


class PluginInstanceConfig(BaseModel):
    """单实例 drop-in 配置（spec 只读 vs instances 可写）。

    Attributes:
        enabled: 该实例是否装配。
        config: 实例策略配置（插件自定义键值）。
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class PluginAssembly(BaseModel):
    """Project 级插件装配清单。

    Attributes:
        enabled: 启用的 plugin_id 清单（列表序即装配序基础）。
        instances: plugin_id → instance_id → 实例配置；multi_instance 插件
            必填 ≥1，单实例插件不得出现（形状校验见 ``validate_assembly``）。
    """

    model_config = ConfigDict(extra="forbid")

    enabled: list[str] = Field(default_factory=list)
    instances: dict[str, dict[str, PluginInstanceConfig]] = Field(default_factory=dict)


def validate_assembly(spec: PluginSpec, assembly: PluginAssembly) -> list[str]:
    """对照 spec 校验 assembly 形状（纯函数，返回错误清单，不 raise）。

    规则：
    - multi_instance 插件在 enabled 中但缺 instances 声明 → 错（列缺失）；
    - 单实例插件出现 instances 条目 → 错；
    - instances 中出现未 enabled 的 plugin_id → 错（装配清单是唯一入口）。
    """

    errors: list[str] = []
    enabled = set(assembly.enabled)
    for plugin_id in assembly.enabled:
        if plugin_id == spec.plugin_id:
            if spec.multi_instance and not assembly.instances.get(plugin_id):
                errors.append(
                    f"multi_instance plugin '{plugin_id}' requires instance "
                    "declarations (assembly.instances) before mount"
                )
            if not spec.multi_instance and plugin_id in assembly.instances:
                errors.append(f"single-instance plugin '{plugin_id}' must not declare instances")
    for plugin_id in assembly.instances:
        if plugin_id not in enabled:
            errors.append(
                f"instances declared for plugin '{plugin_id}' which is not in enabled list"
            )
    return errors
