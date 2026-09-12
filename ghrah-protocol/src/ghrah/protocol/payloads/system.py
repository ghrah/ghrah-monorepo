# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""系统载荷模型（command_result / error）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ─── 系统载荷模型 ───


class CommandResultPayload(BaseModel):
    """command_result 系统载荷。"""

    request_id: str
    success: bool
    data: Any = None
    error: str | None = None
    error_detail: str | None = None


class ErrorPayload(BaseModel):
    """error 系统载荷。"""

    code: str
    message: str
    details: dict[str, Any] | None = None
