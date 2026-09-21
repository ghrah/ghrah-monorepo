# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件注册表：capability → plugin_id 的唯一求解点（集合运算，无 SAT）。

纯内存索引，由启用 spec 列表构造；不含挂载/卸载副作用（归 Subject 侧装配链）。
"""

from __future__ import annotations

from ghrah.plugin.spec import PluginSpec

__all__ = ["PluginRegistry"]


class PluginRegistry:
    """已启用插件的 capability 索引。

    只按 spec ``provides.capabilities`` 原文索引；checker 扩展点用**独立派生索引**
    （由 ``provides.checkers`` 生成 ``core:checker/<name>`` 键），不污染
    ``candidates_snapshot()`` 的原文语义——checker 命中/缺口一律走
    ``resolve_checker``。
    """

    def __init__(self, specs: list[PluginSpec]) -> None:
        self._specs: dict[str, PluginSpec] = {spec.plugin_id: spec for spec in specs}
        self._capability_index: dict[str, list[str]] = {}
        self._checker_index: dict[str, list[str]] = {}
        for spec in self._specs.values():
            for capability in spec.provides.capabilities:
                self._capability_index.setdefault(capability, []).append(spec.plugin_id)
            for checker in spec.provides.checkers:
                self._checker_index.setdefault(checker, []).append(spec.plugin_id)

    @property
    def specs(self) -> dict[str, PluginSpec]:
        """plugin_id → spec 只读视图。"""

        return dict(self._specs)

    def resolve_capability(self, name: str) -> list[str]:
        """求解提供某 capability 的 plugin_id 清单（未命中返回空列表）。"""

        return list(self._capability_index.get(name, ()))

    def resolve_checker(self, name: str) -> list[str]:
        """求解提供某 checker 的 plugin_id 清单（未命中返回空列表）。

        派生自 ``provides.checkers``（键构造 ``core:checker/<name>`` 归本注册表，
        但独立存放；``resolve_capability("core:checker/...")`` 仍只查原文索引）。
        """

        return list(self._checker_index.get(name, ()))

    def candidates_snapshot(self) -> dict[str, list[str]]:
        """capability → 提供者清单快照（CapabilityMissingError.candidates 用）。"""

        return {
            capability: list(providers) for capability, providers in self._capability_index.items()
        }

    def checker_candidates_snapshot(self) -> dict[str, list[str]]:
        """checker 名 → 提供者清单快照（缺口清单 missing_checks.candidates 用）。"""

        return {checker: list(providers) for checker, providers in self._checker_index.items()}

    def check_provides(self, cmd_name: str, declared_provides: list[str]) -> bool:
        """校验视图保存声明的命令是否被已启用插件 provides（权威函数）。

        Args:
            cmd_name: 视图引用的命令名。
            declared_provides: 声明提供该命令的 plugin_id 清单。
        """

        for plugin_id in declared_provides:
            spec = self._specs.get(plugin_id)
            if spec is not None and cmd_name in spec.provides.commands:
                return True
        return False


def sort_for_mount(specs: list[PluginSpec]) -> list[PluginSpec]:
    """按 ``after`` 声明稳定排序（装配顺序求解）。

    - 被引用插件缺失/未启用不阻塞（``after`` 是排序声明，非依赖）：其声明退化为无效果；
    - 结果确定性：无 ``after`` 约束时保持入参列表序（显式、可预测，
      禁止依赖 entry_points 发现顺序等隐式因素）；
    - 使用稳定拓扑排序（Kahn），同约束下保持入参序。
    """

    remaining = list(specs)
    by_id = {spec.plugin_id: spec for spec in remaining}
    # 依赖边：after 中的每个 plugin_id（须在集合内且非自身）先于本插件。
    pending: dict[str, set[str]] = {}
    for spec in remaining:
        deps = {dep for dep in spec.after if dep in by_id and dep != spec.plugin_id}
        pending[spec.plugin_id] = deps

    ordered: list[PluginSpec] = []
    placed: set[str] = set()
    while pending:
        # 稳定：每轮取入参序中第一个依赖已清空的插件。
        ready = next(
            (
                spec.plugin_id
                for spec in remaining
                if spec.plugin_id in pending and not pending[spec.plugin_id]
            ),
            None,
        )
        if ready is None:  # 环：按入参序落完剩余项（after 是排序声明，不做环爆炸）
            for spec in remaining:
                if spec.plugin_id in pending:
                    ordered.append(spec)
            break
        ordered.append(by_id[ready])
        placed.add(ready)
        del pending[ready]
        for deps in pending.values():
            deps.discard(ready)
    assert len(ordered) == len(specs)
    return ordered
