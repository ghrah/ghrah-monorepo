# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace built-in Subject unit."""

from __future__ import annotations

import logging
import os
from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import SANDBOX_EXECUTOR, WORKSPACE_SERVICE
from ghrah.subject.sandbox.executor import SandboxExecutor
from ghrah.subject.sandbox.workspace import WorkspaceManager
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import WORKSPACE_COMMANDS

__all__ = ["WorkspaceUnit"]

logger = logging.getLogger(__name__)


class _WorkspaceServiceAdapter:
    """Typed workspace service adapter backed by WorkspaceManager."""

    def __init__(self, manager: WorkspaceManager) -> None:
        self._manager = manager

    @property
    def root_path(self) -> str:
        return self._manager.root_path

    async def create_workspace(self, agent_name: str) -> Any:
        return await self._manager.create_workspace(agent_name)

    def resolve_agent_path(self, agent_name: str) -> str | None:
        workspace = self._manager.get_workspace(agent_name)
        if workspace is not None:
            return workspace.path
        path = os.path.join(self._manager.root_path, agent_name)
        if os.path.isdir(path):
            return path
        return None

    def resolve_agent_default_path(self, agent_name: str) -> str | None:
        """新名叠加：语义对齐 resolve_agent_path，以 WorkspaceRecord 取向。

        默认回退到 resolve_agent_path（MVP 每 agent 一个默认 workspace）。
        """
        return self.resolve_agent_path(agent_name)

    def get_workspace_record(self, workspace_id: str) -> Any | None:
        return self._manager.get_record(workspace_id)


class WorkspaceUnit(SubjectUnit):
    """Owns WorkspaceManager and workspace command/event routes."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._manager: WorkspaceManager | None = None
        self._service: _WorkspaceServiceAdapter | None = None
        self._meta = UnitMeta(
            name="workspace",
            requires=frozenset({SANDBOX_EXECUTOR}),
            provides=frozenset({WORKSPACE_SERVICE}),
            routes=RouteSpec(
                commands=WORKSPACE_COMMANDS,
                events=frozenset({"agent_spawned", "agent_terminated"}),
            ),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    @property
    def manager(self) -> WorkspaceManager:
        if self._manager is None:
            raise RuntimeError("WorkspaceUnit has not been initialized.")
        return self._manager

    @property
    def service(self) -> _WorkspaceServiceAdapter:
        if self._service is None:
            raise RuntimeError("WorkspaceUnit has not been initialized.")
        return self._service

    async def init(self, ctx: SubjectContext) -> None:
        sandbox = ctx.services.require(SANDBOX_EXECUTOR)
        if not isinstance(sandbox, SandboxExecutor):
            raise TypeError("SANDBOX_EXECUTOR service must be SandboxExecutor.")
        self._manager = WorkspaceManager(
            root_path=ctx.config.sandbox.workspace_root,
            sandbox=sandbox,
            owns_sandbox=False,
            db_path=ctx.config.persistence.db_path,
            subject_id="default",
        )
        self._service = _WorkspaceServiceAdapter(self._manager)
        ctx.services.set(WORKSPACE_SERVICE, self._service)

    async def start(self) -> None:
        await self.manager.start()

    async def stop(self) -> None:
        if self._manager is not None:
            await self._manager.stop()

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        return await self._handle_workspace_command(command, payload)

    async def handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        agent_name = payload.get("name", "")
        if not agent_name:
            return
        if event_type == "agent_spawned":
            await self.manager.create_workspace(agent_name)
        elif event_type == "agent_terminated":
            await self.manager.destroy_workspace(agent_name)

    async def _handle_workspace_command(
        self,
        command: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        agent_name = payload.get("agent_name", "")

        try:
            if command == "create_workspace":
                created_workspace = await self.manager.create_workspace(agent_name)
                return {
                    "success": True,
                    "data": {"agent_name": agent_name, "path": created_workspace.path},
                }

            if command == "destroy_workspace":
                await self.manager.destroy_workspace(agent_name)
                return {
                    "success": True,
                    "data": {"agent_name": agent_name, "destroyed": True},
                }

            if command == "workspace_snapshot":
                snapshot_workspace = self.manager.get_workspace(agent_name)
                if snapshot_workspace is None:
                    return self._workspace_not_found(agent_name)
                commit_hash = await snapshot_workspace.snapshot(
                    message=payload.get("message", "")
                )
                return {
                    "success": True,
                    "data": {"agent_name": agent_name, "snapshot_id": commit_hash},
                }

            if command == "workspace_rollback":
                rollback_workspace = self.manager.get_workspace(agent_name)
                if rollback_workspace is None:
                    return self._workspace_not_found(agent_name)
                snapshot_id = payload.get("snapshot_id", "")
                await rollback_workspace.rollback(snapshot_id)
                return {
                    "success": True,
                    "data": {
                        "agent_name": agent_name,
                        "rolled_back_to": snapshot_id,
                    },
                }

            if command == "workspace_diff":
                diff_workspace = self.manager.get_workspace(agent_name)
                if diff_workspace is None:
                    return self._workspace_not_found(agent_name)
                diff_str = await diff_workspace.diff(snapshot_id=payload.get("snapshot_id"))
                return {
                    "success": True,
                    "data": {"agent_name": agent_name, "diff": diff_str},
                }

            if command == "workspace_status":
                status_workspace = self.manager.get_workspace(agent_name)
                if status_workspace is None:
                    return self._workspace_not_found(agent_name)
                status = await status_workspace.status()
                return {
                    "success": True,
                    "data": {
                        "agent_name": agent_name,
                        "branch": status.branch,
                        "is_clean": status.is_clean,
                        "staged_files": status.staged_files,
                        "unstaged_files": status.unstaged_files,
                        "untracked_files": status.untracked_files,
                    },
                }

            if command == "workspace_register":
                locator = payload.get("locator", "")
                if not locator:
                    return {"success": False, "error": "locator is required"}
                ws = await self.manager.register_workspace(
                    locator,
                    name=payload.get("name", ""),
                    provider_type=payload.get("provider_type"),
                )
                return {
                    "success": True,
                    "data": {
                        "workspace_id": ws.record.workspace_id,
                        "name": ws.record.name,
                        "provider_type": ws.record.provider_type,
                        "locator": ws.record.locator,
                        "path": ws.path,
                    },
                }

            if command == "workspace_get":
                workspace_id = payload.get("workspace_id", "")
                record = self.manager.get_record(workspace_id)
                if record is None:
                    return {
                        "success": False,
                        "error": f"Workspace not found: {workspace_id}",
                    }
                return {
                    "success": True,
                    "data": {
                        "workspace_id": record.workspace_id,
                        "name": record.name,
                        "provider_type": record.provider_type,
                        "subject_id": record.subject_id,
                        "locator": record.locator,
                        "created_at": record.created_at.isoformat(),
                        "updated_at": record.updated_at.isoformat(),
                    },
                }

            if command == "workspace_list":
                provider_type = payload.get("provider_type")
                records = self.manager.list_records_by_provider(provider_type)
                return {
                    "success": True,
                    "data": {
                        "workspaces": [
                            {
                                "workspace_id": r.workspace_id,
                                "name": r.name,
                                "provider_type": r.provider_type,
                                "locator": r.locator,
                            }
                            for r in records
                        ],
                    },
                }

            return {"success": False, "error": f"Unknown workspace command: {command}"}
        except Exception as exc:
            logger.exception("Error handling workspace command %s", command)
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _workspace_not_found(agent_name: str) -> dict[str, Any]:
        return {
            "success": False,
            "error": f"Workspace not found for agent '{agent_name}'",
        }
