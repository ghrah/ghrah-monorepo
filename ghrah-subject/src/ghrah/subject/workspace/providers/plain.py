# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""PlainWorkspaceProvider：纯目录后端（挂载语义下唯一内置 provider）。

provider_type="plain"，capabilities=FILESYSTEM_BACKED。
init: mkdir（仅 create_workspace 路径）；status: 存在性 + 可写性。
对目录零其他物理操作；解挂由 manager 承担（store 软删 + sandbox 授权解除）。
"""

from __future__ import annotations

import logging
import os
from typing import ClassVar

from ghrah.subject._fs import is_writable
from ghrah.subject.workspace.locator import locator_to_path
from ghrah.subject.workspace.models import WorkspaceRecord, WorkspaceStatus
from ghrah.subject.workspace.providers.base import WorkspaceCaps, WorkspaceProvider

__all__ = ["PlainWorkspaceProvider"]

logger = logging.getLogger(__name__)


class PlainWorkspaceProvider(WorkspaceProvider):
    """plain 目录后端 provider（仅 FILESYSTEM_BACKED）。"""

    provider_type: ClassVar[str] = "plain"
    capabilities: ClassVar[WorkspaceCaps] = WorkspaceCaps.FILESYSTEM_BACKED

    async def init(self, record: WorkspaceRecord) -> None:
        """mkdir -p（幂等：目录已存在直接返回）。

        仅 create_workspace（ghrah 新建默认 workspace）路径调用。
        """
        ws_path = locator_to_path(record.locator)
        os.makedirs(ws_path, exist_ok=True)
        logger.info("Initialized plain workspace %s (%s)", record.workspace_id, ws_path)

    async def status(self, record: WorkspaceRecord) -> WorkspaceStatus:
        """存在性 + 可写性。"""
        ws_path = locator_to_path(record.locator)
        exists = os.path.isdir(ws_path)
        writable = is_writable(ws_path) if exists else False
        return WorkspaceStatus(exists=exists, writable=writable, extra={})
