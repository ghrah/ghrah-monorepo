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
from ghrah.protocol.types import GetChainHistoryPayload
from ghrah.subject.config import SubjectConfig
from ghrah.subject.ledger.chain import ActionChainLedger
from ghrah.subject.project.paths import ProjectPaths
from ghrah.subject.runtime.service_keys import LEDGER, PROJECT_MANAGER
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import CHAIN_HISTORY_COMMANDS

__all__ = ["LedgerUnit"]

logger = logging.getLogger(__name__)


class LedgerUnit(SubjectUnit):
    """Owns the read-side ActionChainLedger (Core sqlite projection)."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ledger: ActionChainLedger | None = None
        self._project_ledgers: dict[str, ActionChainLedger] = {}
        self._frozen_projects: set[str] = set()
        self._ctx: Any | None = None
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
        self._ctx = ctx
        # 读侧直连：db 路径从 SubjectConfig.core_db_path 派生（与 registry
        # 构造 CoreUnit 的 persistence_factory 同源），无 requires。
        self._ledger = ActionChainLedger(self._config.core_db_path)
        ctx.provide(LEDGER.name, self._ledger)

    async def start(self) -> None:
        await self.service.start()

    async def stop(self) -> None:
        for ledger in self._project_ledgers.values():
            await ledger.stop()
        self._project_ledgers.clear()
        if self._ledger is not None:
            await self._ledger.stop()

    async def _ledger_for_project(self, project_id: str) -> ActionChainLedger:
        if not project_id:
            raise ValueError("project_id required")
        if self._ctx is None:
            raise ValueError("project_manager unavailable")
        if project_id in self._frozen_projects:
            raise ValueError("resource_archived")
        existing = self._project_ledgers.get(project_id)
        if existing is not None:
            return existing
        try:
            manager = self._ctx.get(PROJECT_MANAGER.name)
            register = getattr(manager, "register_scoped_resource", None)
            if register is not None:
                register(self)
            result = await manager.handle_command("project_get", {"project_id": project_id})
            project = (result.get("data") or {}).get("project")
        except Exception:  # noqa: BLE001
            project = None
        if not project or not project.get("project_root_locator"):
            raise ValueError(f"project not found: {project_id}")
        if project.get("archived_at") or project.get("deleted_at"):
            self._frozen_projects.add(project_id)
            raise ValueError("resource_archived")
        ledger = ActionChainLedger(
            ProjectPaths.from_locator(project["project_root_locator"]).action_chain_db_path
        )
        await ledger.start()
        self._project_ledgers[project_id] = ledger
        return ledger

    async def close_project(self, project_id: str) -> None:
        """Freeze a Project and close its cached ActionChain read handle."""

        self._frozen_projects.add(project_id)
        ledger = self._project_ledgers.pop(project_id, None)
        if ledger is not None:
            await ledger.stop()

    async def restore_project(self, project_id: str) -> None:
        self._frozen_projects.discard(project_id)

    async def evict_project(self, project_id: str) -> None:
        await self.close_project(project_id)
        self._frozen_projects.discard(project_id)

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
        try:
            request = GetChainHistoryPayload.model_validate(payload)
            agent_name = request.agent_name
            agent_id = request.agent_id
            project_id = request.project_id
            branch_name = request.branch_name
            limit = request.limit
            persistence_key = await self._resolve_persistence_key(
                agent_name, project_id=project_id, agent_id=agent_id
            )
            ledger = await self._ledger_for_project(project_id)
            nodes = await ledger.get_chain_history(
                persistence_key,
                branch=branch_name,
                limit=limit,
            )
            serialized = [serialize_node(node) for node in nodes]
            active_session_id = ""
            meta = await ledger.get_chain_meta(persistence_key)
            if meta is not None:
                active_session_id = meta.active_session_id
            return {
                "success": True,
                "data": {
                    "project_id": project_id,
                    "agent_name": agent_name,
                    "agent_id": persistence_key,
                    "branch_name": branch_name,
                    "nodes": serialized,
                    "active_session_id": active_session_id,
                },
            }
        except Exception as exc:
            logger.exception("Failed to get chain history")
            return {"success": False, "error": str(exc)}

    async def _resolve_persistence_key(
        self, agent_name: str, *, project_id: str, agent_id: str
    ) -> str:
        """把显示名解析为 Core checkpoint 使用的稳定 agent_id。

        ContextManager 以 ``agent_id`` 分区 SQLite；读取前验证该稳定身份确实
        属于目标 Project，绝不按全局 name 搜索或回退实例级数据库。
        """
        if not project_id:
            raise ValueError("project_id required")
        if not agent_id:
            raise ValueError("agent_id required")
        if self._ctx is None:
            raise ValueError("project_manager unavailable")
        manager = self._ctx.get(PROJECT_MANAGER.name)
        result = await manager.handle_command("project_get", {"project_id": project_id})
        project = (result.get("data") or {}).get("project") if result.get("success") else None
        if not project:
            raise ValueError(f"project not found: {project_id}")
        matches = [
            agent
            for agent in project.get("agents") or []
            if agent.get("agent_id") == agent_id
        ]
        if len(matches) != 1:
            raise ValueError("agent_project_mismatch")
        if matches[0].get("name") != agent_name:
            raise ValueError("agent_identity_mismatch")
        return agent_id
