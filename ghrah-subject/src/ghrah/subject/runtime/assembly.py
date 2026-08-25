# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Subject 装配层（Ouroboros 形态）——取代旧 SubjectEngine 装配序列。

``assemble_subject(ctx, config, profile)``：
1. ``mount_builtin_units``（coexistence=11 / full=14，逐个挂载等 ACTIVE，
   规避 SQLite 并发开库锁）；
2. 第三方 unit allowlist 挂载（``mount_third_party_units``）；
3. reconcile 启动末尾显式触发（对齐旧 ``engine.start()`` 末尾语义；
   Ouroboros 无 ``internal/status`` 事件，装配完成即全部 ACTIVE）。

Context 所有权归调用方（``async with Context() as ctx:``）；退出时
dispose 全部 fiber（unit.stop 逆序由 Ouroboros 负责）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ghrah.subject.runtime.service_keys import RECONCILIATION_SERVICE
from ghrah.subject.runtime.third_party import mount_third_party_units
from ghrah.subject.units import mount_builtin_units

if TYPE_CHECKING:
    from ouroboros import Context, Fiber  # type: ignore[import-untyped]

    from ghrah.subject.config import SubjectConfig

__all__ = ["assemble_subject"]

logger = logging.getLogger(__name__)


async def assemble_subject(
    ctx: Context,
    config: SubjectConfig,
    *,
    profile: str = "full",
) -> dict[str, Fiber]:
    """装配 Subject 运行时并触发启动期 reconcile（若启用且 recovery unit 在场）。"""

    fibers = await mount_builtin_units(ctx, config, profile=profile)
    fibers.update(await mount_third_party_units(ctx, config))

    if config.recovery.enabled and config.recovery.reconcile_on_start:
        reconcile_service = ctx.get(RECONCILIATION_SERVICE.name, strict=False)
        if reconcile_service is not None:
            try:
                await reconcile_service.reconcile()
            except Exception:
                logger.exception("reconcile on start failed (non-fatal)")
        else:
            logger.info(
                "reconcile_on_start enabled but recovery unit not mounted (profile=%s)",
                profile,
            )

    logger.info("Subject assembled (profile=%s, units=%d)", profile, len(fibers))
    return fibers
