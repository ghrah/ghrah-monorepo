# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""checker 扩展点宿主：Checker 契约、CheckerRegistry 与冻结副本。

checker 签名仅协议类型（Mapping），入参为冻结副本（A16：插件不能意外修改
宿主状态）；返回非法结构时归一为 passed=False（受信代码不拖垮宿主转移）。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from pydantic import ConfigDict

from ghrah.taskstore.models import CheckOutcome as _ModelCheckOutcome

__all__ = [
    "Checker",
    "CheckerRegistry",
    "CheckOutcome",
    "InvalidCheckerResultError",
    "freeze_mapping",
]

logger = logging.getLogger(__name__)

_INVALID_RESULT_DETAIL = "invalid checker result"


class CheckOutcome(_ModelCheckOutcome):
    """归一后的 checker 结果（冻结入 claim；字段 SSOT 在 models.CheckOutcome）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


@runtime_checkable
class Checker(Protocol):
    """checker 契约：(evidence, task, config) -> Mapping。

    Args:
        evidence: 证据冻结快照（kind/ref/digest/payload 只读视图）。
        task: task 冻结快照（含 verification 声明，只读视图）。
        config: 实例配置（P0 恒 {}）。

    Returns:
        ``{"passed": bool, "detail": str | None}``；缺 passed 或类型不符由内核归一。
    """

    def __call__(
        self,
        evidence: Mapping[str, Any],
        task: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class InvalidCheckerResultError(Exception):
    """checker 返回非法结构（内核归一处理，不向调用方抛出）。"""


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """深冻结 Mapping：嵌套 dict/list 全部只读化（修改抛 TypeError）。"""

    frozen: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            frozen[key] = freeze_mapping(item)
        elif isinstance(item, list):
            frozen[key] = tuple(freeze_mapping(i) if isinstance(i, Mapping) else i for i in item)
        elif isinstance(item, dict):
            frozen[key] = freeze_mapping(item)
        else:
            frozen[key] = item
    return MappingProxyType(frozen)


class CheckerRegistry:
    """name → checker callable 的注册表（内核持有，装配层注入/注销）。"""

    def __init__(self) -> None:
        self._checkers: dict[str, Checker] = {}

    def register(self, name: str, checker: Checker) -> None:
        """注册/覆盖 checker（同名后注册者胜，装配顺序由调用方控制）。"""

        self._checkers[name] = checker

    def unregister(self, name: str) -> bool:
        """注销 checker；返回是否命中。"""

        return self._checkers.pop(name, None) is not None

    def resolve(self, name: str) -> Checker | None:
        """按名求解 checker（未命中返回 None，缺口归 kernel 记录候选）。"""

        return self._checkers.get(name)

    def candidates(self) -> list[str]:
        """已注册 checker 名清单（稳定排序，供快照与测试）。"""

        return sorted(self._checkers)


def normalize_result(checker: str, result: Mapping[str, Any]) -> CheckOutcome:
    """归一 checker 返回：缺 passed 或类型不符 → passed=False（不炸宿主）。"""

    passed = result.get("passed")
    detail = result.get("detail")
    if not isinstance(passed, bool) or (detail is not None and not isinstance(detail, str)):
        logger.warning("checker '%s' returned invalid result; normalized to failed.", checker)
        return CheckOutcome(checker=checker, passed=False, detail=_INVALID_RESULT_DETAIL)
    return CheckOutcome(checker=checker, passed=passed, detail=detail)


def run_checker(
    checker: Checker,
    name: str,
    *,
    evidence: Mapping[str, Any],
    task: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> CheckOutcome:
    """执行单个 checker：冻结入参 → 调用 → 归一返回（异常也归一为失败）。"""

    frozen_evidence = freeze_mapping(evidence)
    frozen_task = freeze_mapping(task)
    frozen_config = freeze_mapping(config or {})
    try:
        result = checker(frozen_evidence, frozen_task, frozen_config)
        if not isinstance(result, Mapping):
            raise InvalidCheckerResultError(f"non-mapping result: {type(result).__name__}")
    except Exception as exc:  # noqa: BLE001 — 受信代码不拖垮宿主转移
        logger.warning("checker '%s' raised: %s; normalized to failed.", name, exc)
        return CheckOutcome(checker=name, passed=False, detail=f"checker error: {exc}")
    return normalize_result(name, result)
