# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""loader 测试用的可导入 spec 目标模块（entry_point 导入式发现）。"""

from __future__ import annotations

from ghrah.plugin.spec import PluginSpec

spec_a = PluginSpec(plugin_id="plugin-a", version="1.0.0")

spec_b = PluginSpec(plugin_id="plugin-b", version="2.0.0", prefix="b:")


def factory_b() -> PluginSpec:
    return spec_b


spec_dup_a = PluginSpec(plugin_id="plugin-a", version="3.0.0")

not_a_spec = object()


def explode() -> PluginSpec:
    raise RuntimeError("boom")
