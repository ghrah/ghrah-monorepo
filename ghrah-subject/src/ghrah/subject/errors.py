# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""稳定错误码契约。

失败回执统一为 ``{"success": False, "data": None, "error": <稳定码>,
"error_detail": <人类可读细节>}``：前端/测试按 ``error`` 精确匹配，
``error_detail`` 只做诊断展示。``StableError`` 是 ValueError 子类，
既有的 ``except ValueError`` 错误面无需全部改写；dispatcher 侧优先
捕获本类以输出双字段回执。
"""

from __future__ import annotations

__all__ = ["StableError"]


class StableError(ValueError):
    """携带稳定机器码 + 人类可读细节的错误。

    Attributes:
        code: 稳定机器码（如 ``agent_name_exists``、``cluster_owner_conflict``），
            作为 wire 契约冻结，调用方按此匹配。
        detail: 人类可读细节（含上下文变量），仅用于日志与展示。
    """

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail
