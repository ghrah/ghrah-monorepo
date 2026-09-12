# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""持久化命令载荷模型（Core → Subject）。

注意：Persist* schema 与实际 wire shape 尚不符，未登记 PAYLOAD_MAP（Stage 2 补齐）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PersistSavePayload(BaseModel):
    """persist_save 命令载荷。

    Core → Subject：请求 Subject 保存持久化数据。
    """

    key: str
    data: dict[str, Any]
    namespace: str = "default"


class PersistLoadPayload(BaseModel):
    """persist_load 命令载荷。

    Core → Subject：请求 Subject 加载持久化数据。
    """

    key: str
    namespace: str = "default"


class PersistDeletePayload(BaseModel):
    """persist_delete 命令载荷。

    Core → Subject：请求 Subject 删除持久化数据。
    """

    key: str
    namespace: str = "default"


class PersistListPayload(BaseModel):
    """persist_list 命令载荷。

    Core → Subject：请求 Subject 列出持久化数据。
    """

    namespace: str = "default"
    prefix: str | None = None
