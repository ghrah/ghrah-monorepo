# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件挂载/装配错误类型。

S0 仅定义形态（供 verify 输出与测试消费）；S2 owner 表挂载期爆炸复用。
"""

from __future__ import annotations

__all__ = ["CapabilityMissingError", "PluginMountError"]


class PluginMountError(Exception):
    """插件挂载/装配失败（挂期爆炸，非运行期静默遮蔽）。

    消息应携带定位信息（如现任 owner 名、缺失项清单），
    供调用方直接展示或 Agent 消费。
    """


class CapabilityMissingError(PluginMountError):
    """硬 capability 缺失导致拒启。

    Attributes:
        missing: 缺失的 capability 名清单。
        candidates: capability → 提供该 capability 的 plugin_id 清单
            （可供候选，供 Agent 消费决策启用谁）。
    """

    def __init__(self, missing: list[str], candidates: dict[str, list[str]]) -> None:
        self.missing = missing
        self.candidates = candidates
        parts = [f"missing capabilities: {', '.join(missing)}"]
        for capability, providers in candidates.items():
            if providers:
                parts.append(f"  {capability} provided by: {', '.join(providers)}")
        super().__init__(
            "Plugin mount rejected: "
            + "; ".join(parts)
            + (" (no candidates available)" if not any(candidates.values()) else "")
        )
