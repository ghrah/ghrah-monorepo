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

    async def _ledger_for_project(self, project_id: str | None) -> ActionChainLedger:
        if not project_id or self._ctx is None:
            return self.service
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
            return self.service
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

    async def _project_ids(self) -> list[str]:
        if self._ctx is None:
            return []
        try:
            manager = self._ctx.get(PROJECT_MANAGER.name)
            result = await manager.handle_command("project_list", {})
            return [
                project["project_id"]
                for project in (result.get("data") or {}).get("projects", [])
                if project.get("project_root_locator")
            ]
        except Exception:  # noqa: BLE001
            return []

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
        agent_name = str(payload.get("agent_name") or "")
        agent_id = str(payload.get("agent_id") or "")
        project_id = payload.get("project_id")
        branch_name = payload.get("branch_name", "main")
        limit = payload.get("limit", -1)

        if not agent_name:
            return {"success": False, "error": "agent_name is required"}

        try:
            persistence_key = await self._resolve_persistence_key(
                agent_name, project_id=str(project_id or ""), agent_id=agent_id
            )
            if project_id:
                ledgers = [await self._ledger_for_project(project_id)]
            else:
                # Old callers did not carry project_id. Prefer project roots and
                # retain the global DB as the final compatibility fallback.
                ledgers = [
                    await self._ledger_for_project(pid)
                    for pid in await self._project_ids()
                ]
                ledgers.append(self.service)
            ledger = ledgers[-1]
            nodes = []
            for candidate in ledgers:
                candidate_nodes = await candidate.get_chain_history(
                    persistence_key,
                    branch=branch_name,
                    limit=limit,
                )
                if candidate_nodes:
                    ledger = candidate
                    nodes = candidate_nodes
                    break
            serialized = [serialize_node(node) for node in nodes]
            active_session_id = ""
            meta = await ledger.get_chain_meta(persistence_key)
            if meta is not None:
                active_session_id = meta.active_session_id
            return {
                "success": True,
                "data": {
                    "agent_name": agent_name,
                    "agent_id": persistence_key if persistence_key != agent_name else agent_id,
                    "branch_name": branch_name,
                    "nodes": serialized,
                    "active_session_id": active_session_id,
                },
            }
        except Exception as exc:
            logger.exception("Failed to get chain history for %s", agent_name)
            return {"success": False, "error": str(exc)}

    async def _resolve_persistence_key(
        self, agent_name: str, *, project_id: str, agent_id: str
    ) -> str:
        """把显示名解析为 Core checkpoint 使用的稳定 agent_id。

        UUID 引入后 ContextManager 以 ``agent_id`` 分区 SQLite；旧 Observer 仍只
        发送 ``agent_name + project_id``。在 Ledger 边界完成兼容解析，避免 Agent
        已恢复但 ActionChain 初始投影查询空桶。
        """
        if agent_id:
            return agent_id
        if not project_id or self._ctx is None:
            return agent_name
        manager = self._ctx.get(PROJECT_MANAGER.name)
        result = await manager.handle_command("project_get", {"project_id": project_id})
        project = (result.get("data") or {}).get("project") if result.get("success") else None
        if not project:
            return agent_name
        matches = [
            agent
            for agent in project.get("agents") or []
            if agent.get("name") == agent_name
        ]
        if len(matches) > 1:
            raise ValueError(f"ambiguous agent name in project: {agent_name}")
        if len(matches) == 1 and matches[0].get("agent_id"):
            return str(matches[0]["agent_id"])
        # 兼容未进入 Project desired-state 的旧 ephemeral Agent checkpoint。
        return agent_name
