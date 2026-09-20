# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""协商纯函数（S0 定义在本包；S1 包装进 protocol payload，A9）。

输入 Python 侧注册表快照 + TS 侧上报清单，输出协商结果；
零 IO、零状态——连接级与变更级两条触发路径共用（A10）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ghrah.plugin.spec import PluginSpec
from ghrah.plugin.verify import check_capability_closure

__all__ = [
    "MatchedPlugin",
    "NegotiationResult",
    "PythonHalfInfo",
    "TsHalfReport",
    "VersionConflict",
    "negotiate",
    "python_half_from_spec",
]


class PythonHalfInfo(BaseModel):
    """Python 半插件信息（注册表快照条目）。"""

    plugin_id: str
    version: str
    provides: list[str] = Field(default_factory=list)
    requires_capabilities: list[str] = Field(default_factory=list)
    instances: list[str] = Field(default_factory=list)


class TsHalfReport(BaseModel):
    """TS 半插件上报条目。"""

    plugin_id: str
    version: str
    provides: list[str] = Field(default_factory=list)


class MatchedPlugin(BaseModel):
    """双侧在场且版本一致的插件。"""

    plugin_id: str
    version: str
    provides: list[str]
    instances: list[str] = Field(default_factory=list)


class VersionConflict(BaseModel):
    """双侧在场但版本不一致。"""

    plugin_id: str
    python_version: str
    ts_version: str


class NegotiationResult(BaseModel):
    """协商结果（父计划 §2.1 negotiator 响应结构）。"""

    matched: list[MatchedPlugin] = Field(default_factory=list)
    python_only: list[PythonHalfInfo] = Field(default_factory=list)
    ts_only: list[TsHalfReport] = Field(default_factory=list)
    version_conflicts: list[VersionConflict] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    instances: dict[str, list[str]] = Field(default_factory=dict)


def python_half_from_spec(
    spec: PluginSpec, *, instances: list[str] | None = None
) -> PythonHalfInfo:
    """从 PluginSpec 构造 PythonHalfInfo（provides 拍平为字符串清单）。"""

    provides: list[str] = [
        *(f"checker/{name}" for name in spec.provides.checkers),
        *(f"evidence-kind/{name}" for name in spec.provides.evidence_kinds),
        *(f"command/{name}" for name in spec.provides.commands),
        *spec.provides.capabilities,
    ]
    return PythonHalfInfo(
        plugin_id=spec.plugin_id,
        version=spec.version,
        provides=provides,
        requires_capabilities=list(spec.requires.capabilities),
        instances=list(instances or []),
    )


def negotiate(python: list[PythonHalfInfo], ts: list[TsHalfReport]) -> NegotiationResult:
    """对照双侧清单得出协商结果（纯函数）。

    - matched：双侧在场且 version 相等（D6：仅相等比较）；
    - python_only / ts_only：单侧在场；
    - version_conflicts：双侧在场但版本不等；
    - missing_capabilities：Python 侧 requires 并集 − 双侧 provides 并集
      （复用 verify 闭环函数，D5）。
    """

    py_by_id = {item.plugin_id: item for item in python}
    ts_by_id = {item.plugin_id: item for item in ts}

    matched: list[MatchedPlugin] = []
    conflicts: list[VersionConflict] = []
    for plugin_id, py in py_by_id.items():
        ts_item = ts_by_id.get(plugin_id)
        if ts_item is None:
            continue
        if ts_item.version == py.version:
            merged = list(dict.fromkeys([*py.provides, *ts_item.provides]))
            matched.append(
                MatchedPlugin(
                    plugin_id=plugin_id,
                    version=py.version,
                    provides=merged,
                    instances=list(py.instances),
                )
            )
        else:
            conflicts.append(
                VersionConflict(
                    plugin_id=plugin_id,
                    python_version=py.version,
                    ts_version=ts_item.version,
                )
            )

    missing, _candidates = check_capability_closure(
        requires=[capability for item in python for capability in item.requires_capabilities],
        provides=[(None, capability) for item in python for capability in item.provides]
        + [(None, capability) for item in ts for capability in item.provides],
    )

    return NegotiationResult(
        matched=matched,
        python_only=[item for plugin_id, item in py_by_id.items() if plugin_id not in ts_by_id],
        ts_only=[item for plugin_id, item in ts_by_id.items() if plugin_id not in py_by_id],
        version_conflicts=conflicts,
        missing_capabilities=missing,
        instances={item.plugin_id: list(item.instances) for item in python},
    )
