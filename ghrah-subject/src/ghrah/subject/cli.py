# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``subject`` CLI 入口（argparse，仓内无框架先例不引入 click/typer）。

首个子命令链 ``subject plugin verify [--all]``（A18 离线验证，
systemd-analyze verify 同构）：不启动 Subject 即可检查 spec 语法、
capability 闭环、版本冲突、owner 撞名。

退出码：0 = 无 error 型 finding；1 = 存在 error；2 = 环境错误。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from ghrah.plugin.loader import discover_plugins
from ghrah.plugin.spec import PluginSpec
from ghrah.plugin.verify import Finding, verify_plugins

from ghrah.subject.config import SubjectConfig

__all__ = ["main"]

_EXIT_OK = 0
_EXIT_FINDINGS = 1
_EXIT_ENV_ERROR = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subject",
        description="ghrah Subject 离线工具（不启动 Subject 进程）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plugin_parser = subparsers.add_parser("plugin", help="插件管理（离线验证）")
    plugin_subparsers = plugin_parser.add_subparsers(dest="plugin_command", required=True)

    verify_parser = plugin_subparsers.add_parser(
        "verify",
        help="离线验证插件：spec 语法、capability 闭环、版本冲突、owner 撞名",
    )
    verify_parser.add_argument(
        "--all",
        action="store_true",
        help="验证全部已发现插件（忽略信任清单过滤；供发行版 CI）",
    )
    return parser


def _core_version() -> str | None:
    """读 ghrah-core dist 元数据（不 import ghrah 域代码，不违 A9）。"""

    try:
        return version("ghrah-core")
    except PackageNotFoundError:
        return None


def _format_finding(finding: Finding) -> str:
    scope = finding.plugin_id or "<global>"
    return f"[{finding.severity}] {finding.kind} ({scope}): {finding.message}"


def _verify_plugins_command(*, check_all: bool) -> int:
    from ghrah.plugin.loader import LoadIssue

    discovered, load_issues = discover_plugins()
    config = SubjectConfig.from_env()

    if check_all:
        selected = [item.spec for item in discovered]
        untrusted: list[PluginSpec] = []
    else:
        trusted = config.plugin_trust.trust_set
        if not trusted:
            print("no plugins to verify (trust list is empty; use --all to check all discovered)")
            return _EXIT_OK
        selected = [item.spec for item in discovered if item.spec.plugin_id in trusted]
        untrusted = [item.spec for item in discovered if item.spec.plugin_id not in trusted]
        discovered_ids = {item.spec.plugin_id for item in discovered}
        ghost_issues = [
            LoadIssue(
                entry_point=plugin_id,
                error="plugin is trusted but was not discovered via entry_points",
            )
            for plugin_id in sorted(trusted - discovered_ids)
        ]
        load_issues = [*load_issues, *ghost_issues]

    findings = verify_plugins(
        selected,
        load_issues=load_issues,
        core_version=_core_version(),
        candidate_provides=[
            (spec.plugin_id, capability)
            for spec in untrusted
            for capability in spec.provides.capabilities
        ],
    )

    if not selected and not load_issues and not findings:
        print("no plugins discovered")
        return _EXIT_OK

    for finding in findings:
        print(_format_finding(finding))
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = len(findings) - errors
    scope = "all discovered" if check_all else "trusted"
    print(
        f"verify complete ({scope}): "
        f"{len(selected)} plugin(s), {errors} error(s), {warnings} warning(s)"
    )
    return _EXIT_OK if errors == 0 else _EXIT_FINDINGS


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口（返回退出码；console script 直用本函数）。"""

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "plugin" and args.plugin_command == "verify":
        try:
            return _verify_plugins_command(check_all=args.all)
        except Exception as exc:  # 环境错误（entry_points 读取异常等）
            print(f"verify failed: {exc}", file=sys.stderr)
            return _EXIT_ENV_ERROR
    parser.error(f"unknown command: {args.command}")
    return _EXIT_ENV_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
