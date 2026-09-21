# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""loader 测试用的可导入 spec 目标模块（entry_point 导入式发现）。"""

from __future__ import annotations

from ghrah.plugin.spec import PluginSpec


class UnitStub:
    """宿主 unit 形态占位（loader 仅探测工厂存在性，不校验具体类型）。"""


spec_a = PluginSpec(plugin_id="plugin-a", version="1.0.0")

spec_b = PluginSpec(plugin_id="plugin-b", version="2.0.0", prefix="b:")


def factory_b() -> PluginSpec:
    return spec_b


spec_dup_a = PluginSpec(plugin_id="plugin-a", version="3.0.0")

not_a_spec = object()


def explode() -> PluginSpec:
    raise RuntimeError("boom")


# ── 模块形态 entry point：模块暴露 spec + unit 工厂 ──
plugin_spec = PluginSpec(plugin_id="plugin-module", version="1.0.0")


def create_unit() -> UnitStub:
    return UnitStub()


# ── PluginSpec 子类形态：类属性声明 unit 工厂 ──
class _SubSpec(PluginSpec):
    @staticmethod
    def unit_factory() -> UnitStub:
        return UnitStub()


sub_spec = _SubSpec(plugin_id="plugin-sub", version="1.0.0")


# ── checker 工厂形态：模块暴露 create_checker（签名 (name) -> callable）──
def create_checker(name: str):  # noqa: ANN201 — 探测只验 callable
    def checker(evidence, task, config):  # noqa: ANN001, ANN202
        return {"passed": True}

    return checker


# ── PluginSpec 子类形态：类属性声明 checker 工厂 ──
class _CheckerSubSpec(PluginSpec):
    @staticmethod
    def checker_factory(name: str):  # noqa: ANN202 — 探测只验 callable
        return lambda evidence, task, config: {"passed": True}


checker_sub_spec = _CheckerSubSpec(plugin_id="plugin-checker-sub", version="1.0.0")
