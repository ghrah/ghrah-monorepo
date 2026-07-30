# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""结构化 workspace marker 读写（.ghrah-workspace）。

按计划 §2.6：从一行注释升级为 JSON，认领校验三要素
（workspace_id / provider_type / subject_id）。

marker 内容：
    {"workspace_id": "...", "provider_type": "git", "subject_id": "default",
     "created_at": "..."}

旧格式 marker（一行注释）视为不可机读 → 不自动认领（adopt 返回 None），
由调用方 log 提示并提供 workspace_register 手动登记路径。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ghrah.subject.workspace.models import WorkspaceRecord

__all__ = [
    "MARKER_FILENAME",
    "MarkerData",
    "read_marker",
    "write_marker",
]

MARKER_FILENAME = ".ghrah-workspace"


@dataclass(frozen=True)
class MarkerData:
    """从结构化 marker 解析出的认领三要素 + 元数据。"""

    workspace_id: str
    provider_type: str
    subject_id: str
    created_at: str | None
    name: str | None


def write_marker(dir_path: str, record: WorkspaceRecord) -> None:
    """写结构化 JSON marker（幂等覆盖）。

    Args:
        dir_path: workspace 目录绝对路径。
        record: 对应的 WorkspaceRecord。
    """
    marker_path = os.path.join(dir_path, MARKER_FILENAME)
    payload = {
        "workspace_id": record.workspace_id,
        "provider_type": record.provider_type,
        "subject_id": record.subject_id,
        "created_at": record.created_at.isoformat(),
        "name": record.name,
    }
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        f.write("\n")


def read_marker(dir_path: str) -> MarkerData | None:
    """读结构化 marker。

    Returns:
        解析出的 MarkerData；marker 不存在、非 JSON、或缺少必要字段时返回 None
        （旧格式一行注释 marker 会在 JSON 解析阶段被识别为不可机读 → None）。
    """
    marker_path = os.path.join(dir_path, MARKER_FILENAME)
    if not os.path.isfile(marker_path):
        return None
    try:
        with open(marker_path, encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw or not raw.startswith("{"):
            # 旧格式（一行注释 "# ..."）不可机读
            return None
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return MarkerData(
            workspace_id=str(data["workspace_id"]),
            provider_type=str(data["provider_type"]),
            subject_id=str(data["subject_id"]),
            created_at=data.get("created_at"),
            name=data.get("name"),
        )
    except (KeyError, TypeError):
        return None


def marker_path(dir_path: str) -> str:
    """返回 marker 文件完整路径。"""
    return os.path.join(dir_path, MARKER_FILENAME)
