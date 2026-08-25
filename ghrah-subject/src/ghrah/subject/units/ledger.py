# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Action-chain ledger built-in Subject unit（读侧直连 Core sqlite）。

聚合裁决 D-C：``chain_history`` 读命令经 :class:`ActionChainLedger`
（Core ``SqliteBackend`` 同文件 WAL 双连接）直读真相源；无写侧
（旧 ``event/action_chain_updated`` 事件驱动落库面已死，删除）。
"""

from __future__ import annotations

import logging
from typing import Any

from ghrah.context.persistence import serialize_node  # type: ignore[import-untyped]
from ghrah.subject.config import SubjectConfig
from ghrah.subject.ledger.chain import ActionChainLedger
from ghrah.subject.runtime.service_keys import LEDGER
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import CHAIN_HISTORY_COMMANDS

__all__ = ["LedgerUnit"]

logger = logging.getLogger(__name__)


class LedgerUnit(SubjectUnit):
    """Owns the read-side ActionChainLedger (Core sqlite projection)."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ledger: ActionChainLedger | None = None
        self._meta = UnitMeta(
            name="ledger",
            provides=frozenset({LEDGER}),
            routes=RouteSpec(commands=CHAIN_HISTORY_COMMANDS),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def service(self) -> ActionChainLedger:
        if self._ledger is None:
            raise RuntimeError("LedgerUnit has not been initialized.")
        return self._ledger

    async def init(self, ctx: Any) -> None:
        # 读侧直连：db 路径从 SubjectConfig.core_db_path 派生（与 registry
        # 构造 CoreUnit 的 persistence_factory 同源），无 requires。
        self._ledger = ActionChainLedger(self._config.core_db_path)
        ctx.provide(LEDGER.name, self._ledger)

    async def start(self) -> None:
        await self.service.start()

    async def stop(self) -> None:
        if self._ledger is not None:
            await self._ledger.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        if command not in CHAIN_HISTORY_COMMANDS:
            return {"success": False, "error": f"Unknown ledger command: {command}"}
        return await self._handle_chain_history(payload)

    async def _handle_chain_history(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_name = payload.get("agent_name", "")
        branch_name = payload.get("branch_name", "main")
        limit = payload.get("limit", -1)

        if not agent_name:
            return {"success": False, "error": "agent_name is required"}

        try:
            nodes = await self.service.get_chain_history(
                agent_name,
                branch=branch_name,
                limit=limit,
            )
            serialized = [serialize_node(node) for node in nodes]
            active_session_id = ""
            meta = await self.service.get_chain_meta(agent_name)
            if meta is not None:
                active_session_id = meta.active_session_id
            return {
                "success": True,
                "data": {
                    "agent_name": agent_name,
                    "branch_name": branch_name,
                    "nodes": serialized,
                    "active_session_id": active_session_id,
                },
            }
        except Exception as exc:
            logger.exception("Failed to get chain history for %s", agent_name)
            return {"success": False, "error": str(exc)}
