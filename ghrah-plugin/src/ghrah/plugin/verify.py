# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""离线验证引擎（A18，systemd-analyze verify 同构）。

纯函数：输入 specs + 发现问题 + core 版本，输出 findings 清单。
CLI（``subject plugin verify``）只是薄适配；发行版 CI 可直接复用引擎。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ghrah.plugin.loader import LoadIssue
from ghrah.plugin.spec import PluginSpec

__all__ = [
    "Finding",
    "FindingKind",
    "check_capability_closure",
    "verify_plugins",
]

FindingKind = Literal[
    "spec_invalid",
    "load_failed",
    "capability_missing",
    "version_conflict",
    "command_conflict",
    "not_discovered",
]


@dataclass(frozen=True)
class Finding:
    """一条验证结果。

    Attributes:
        severity: error（影响挂载/闭环）或 warning（环境缺失等）。
        plugin_id: 关联插件（整体性问题为 None）。
        kind: 问题类别。
        message: 人读摘要。
    """

    severity: Literal["error", "warning"]
    plugin_id: str | None
    kind: FindingKind
    message: str


def check_capability_closure(
    *,
    requires: list[str],
    provides: list[tuple[str | None, str]],
) -> tuple[list[str], dict[str, list[str]]]:
    """capability 闭环检查（D5 SSOT：negotiator 复用同函数）。

    Args:
        requires: 全部插件的 requires.capabilities 并集。
        provides: (提供者 plugin_id, capability) 对的并集
            （提供者未知可传 None，如 TS 半上报的通用条目）。

    Returns:
        (缺失 capability 清单, capability → 提供者候选清单)。
    """

    required = set(requires)
    provided = {capability for _, capability in provides}
    missing = sorted(required - provided)
    candidates = {
        capability: sorted(
            {plugin_id for plugin_id, provided_cap in provides if provided_cap == capability}
        )
        for capability in missing
    }
    return missing, candidates


def _core_version_findings(specs: list[PluginSpec], core_version: str | None) -> list[Finding]:
    constrained = [spec for spec in specs if spec.requires.core_version is not None]
    if not constrained:
        return []
    if core_version is None:
        return [
            Finding(
                severity="warning",
                plugin_id=None,
                kind="version_conflict",
                message="ghrah-core distribution not installed; "
                "requires.core_version constraints were not checked",
            )
        ]
    from packaging.specifiers import SpecifierSet

    findings: list[Finding] = []
    for spec in constrained:
        constraint = spec.requires.core_version
        assert constraint is not None
        if not SpecifierSet(constraint).contains(core_version):
            findings.append(
                Finding(
                    severity="error",
                    plugin_id=spec.plugin_id,
                    kind="version_conflict",
                    message=f"requires.core_version {constraint!r} not satisfied "
                    f"by installed ghrah-core {core_version}",
                )
            )
    return findings


def verify_plugins(
    specs: list[PluginSpec],
    *,
    load_issues: list[LoadIssue] | None = None,
    core_version: str | None = None,
    candidate_provides: list[tuple[str, str]] | None = None,
) -> list[Finding]:
    """离线验证：spec 语法（经 LoadIssue）、capability 闭环、版本、owner 撞名。

    Args:
        specs: 待验证的合法 PluginSpec 清单（发现期已过 schema 校验）。
        load_issues: 发现失败条目（转 load_failed findings）。
        core_version: ghrah-core 版本（None = 未安装，降级为 warning）。
        candidate_provides: 候选提供者上下文（如发现但未信任的插件），
            仅用于丰富 capability_missing 的候选清单，不参与闭环判定。
    """

    findings: list[Finding] = []
    for issue in load_issues or []:
        findings.append(
            Finding(
                severity="error",
                plugin_id=None,
                kind="load_failed",
                message=f"[{issue.entry_point}] {issue.error}",
            )
        )

    # capability 闭环：requires 并集 − provides 并集（A3 探针：错误列候选插件）。
    requires = [capability for spec in specs for capability in spec.requires.capabilities]
    provides = [
        (spec.plugin_id, capability) for spec in specs for capability in spec.provides.capabilities
    ]
    missing, candidates = check_capability_closure(requires=requires, provides=provides)
    if missing:
        if candidate_provides:
            extras = {
                capability: sorted(
                    plugin_id
                    for plugin_id, provided_cap in candidate_provides
                    if provided_cap == capability
                )
                for capability in missing
            }
            for capability, extra_providers in extras.items():
                if extra_providers:
                    candidates[capability] = sorted({*candidates[capability], *extra_providers})
        detail = "; ".join(
            f"{capability} (candidates: {', '.join(candidates[capability]) or 'none'})"
            for capability in missing
        )
        findings.append(
            Finding(
                severity="error",
                plugin_id=None,
                kind="capability_missing",
                message=f"capability closure failed; missing: {detail}",
            )
        )

    findings.extend(_core_version_findings(specs, core_version))

    # owner 撞名（A1 离线前置形态）：provides.commands 跨插件重名。
    command_owners: dict[str, str] = {}
    for spec in specs:
        for command in spec.provides.commands:
            owner = command_owners.get(command)
            if owner is not None and owner != spec.plugin_id:
                findings.append(
                    Finding(
                        severity="error",
                        plugin_id=spec.plugin_id,
                        kind="command_conflict",
                        message=f"command {command!r} already provided by {owner!r} (A1)",
                    )
                )
            else:
                command_owners[command] = spec.plugin_id

    return findings
