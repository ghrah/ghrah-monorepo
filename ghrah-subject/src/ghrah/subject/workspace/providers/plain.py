# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""PlainWorkspaceProvider：无版本能力的纯目录后端。

按计划 §2.5：provider_type="plain"，capabilities=FILESYSTEM_BACKED（无版本能力）。
init: mkdir -p + 写 marker；status: 存在性 + 可写性；destroy: 递归删除。
用途：数据目录、构建产物目录、不需要版本能力的工作区。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import ClassVar

from ghrah.subject.workspace.marker import read_marker, write_marker
from ghrah.subject.workspace.models import AdoptResult, WorkspaceRecord, WorkspaceStatus
from ghrah.subject.workspace.providers.base import WorkspaceCaps, WorkspaceProvider
from ghrah.subject.workspace.providers.git import locator_to_path

__all__ = ["PlainWorkspaceProvider"]

logger = logging.getLogger(__name__)


class PlainWorkspaceProvider(WorkspaceProvider):
    """plain 目录后端 provider（仅 FILESYSTEM_BACKED）。"""

    provider_type: ClassVar[str] = "plain"
    capabilities: ClassVar[WorkspaceCaps] = WorkspaceCaps.FILESYSTEM_BACKED

    async def init(self, record: WorkspaceRecord) -> None:
        """mkdir -p + 写结构化 marker。

        幂等：目录已存在且 marker 匹配三要素则认领式返回。
        """
        ws_path = locator_to_path(record.locator)
        existing_marker = read_marker(ws_path)
        if existing_marker is not None and (
            existing_marker.workspace_id == record.workspace_id
            and existing_marker.provider_type == record.provider_type
            and existing_marker.subject_id == record.subject_id
        ):
            logger.debug(
                "Plain workspace %s already initialized (marker match)", record.locator
            )
            return
        os.makedirs(ws_path, exist_ok=True)
        write_marker(ws_path, record)
        logger.info("Initialized plain workspace %s (%s)", record.workspace_id, ws_path)

    async def adopt(self, locator: str) -> AdoptResult | None:
        """读 marker 校验 provider_type 一致；无 marker / 旧格式 /
        marker 声明非 plain 类型 → 返回 None（不误认领）。
        """
        ws_path = locator_to_path(locator)
        marker = read_marker(ws_path)
        if marker is None or marker.provider_type != self.provider_type:
            return None
        return AdoptResult(
            workspace_id=marker.workspace_id,
            provider_type=marker.provider_type,
            subject_id=marker.subject_id,
            name=marker.name or "",
            created_at=marker.created_at,
        )

    async def status(self, record: WorkspaceRecord) -> WorkspaceStatus:
        """存在性 + 可写性。"""
        ws_path = locator_to_path(record.locator)
        exists = os.path.isdir(ws_path)
        writable = os.access(ws_path, os.W_OK) if exists else False
        return WorkspaceStatus(exists=exists, writable=writable, extra={})

    async def destroy(self, record: WorkspaceRecord) -> None:
        """递归删除目录。"""
        ws_path = locator_to_path(record.locator)
        if os.path.exists(ws_path):
            await asyncio.to_thread(shutil.rmtree, ws_path)
        logger.info("Destroyed plain workspace %s at %s", record.workspace_id, ws_path)
