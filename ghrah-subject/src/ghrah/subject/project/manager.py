# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ProjectManager：13 project 命令编排 + 校验 + bootstrap 高层方法。

- 透传 13 个 ``project_*`` 命令（乐观锁 + 状态流转 + workspace 挂载禁嵌套 +
  path_grants 不重叠 + 实例 manifest 协调）。
- ``bootstrap_default_project`` / ``adopt_existing_agents``：S4.6 reconcile
  首启 bootstrap 专用（决策 2），经 CoreClusterRegistry + WorkspaceManager
  建 default cluster + default workspace + 从 Core list_agents 归入现有 agent。

依赖经构造注入：``cluster_registry`` 为 ``CoreClusterRegistryService``（Protocol），
``workspace_mgr`` 为具体 ``WorkspaceManager``（位于 ``ghrah.subject.sandbox.workspace``，
非 ``ghrah.subject.workspace.manager``，v1 误标）。不依赖 SubjectContext，便于独立单测。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import ValidationError

from ghrah.protocol.types import (
    AgentConfigPayload,
    ProjectAddAgentPayload,
    ProjectCreatePayload,
    ProjectDeletePayload,
    ProjectIdPayload,
    ProjectLinkTaskPayload,
    ProjectListPayload,
    ProjectRemoveAgentPayload,
    ProjectSetRecoveryPayload,
    ProjectUnlinkTaskPayload,
    ProjectUpdatePayload,
    RecoveryAction,
    SpawnAgentPayload,
)
from ghrah.subject.project.isolation import (
    validate_path_grants_non_overlapping,
    validate_workspace_locators_non_nested,
)
from ghrah.subject.project.models import (
    AgentSpec,
    PathGrant,
    ProjectRecord,
    ProjectStatus,
    RecoverySpec,
    WorkspaceMount,
    can_transition,
    make_project_record,
)
from ghrah.subject.project.paths import (
    ProjectPaths,
    canonical_file_locator,
    validate_project_path_boundaries,
)
from ghrah.subject.project.store import (
    ConcurrentModificationError,
    ProjectNotFoundError,
    ProjectStore,
)
from ghrah.subject.workspace.providers.git import path_to_locator

if TYPE_CHECKING:
    from ghrah.subject.manifest_store.store import ManifestStore
    from ghrah.subject.runtime.service_keys import (
        CoreClusterRegistryService as ClusterRegistryProtocol,
    )
    from ghrah.subject.runtime.service_keys import (
        TaskManagerService,
    )
    from ghrah.subject.sandbox.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

__all__ = ["ProjectManager"]

OnEvent = Callable[[str, dict[str, Any]], Awaitable[None]]


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict[str, Any]:
    return {"success": False, "data": None, "error": msg}


def _normalize_locator(locator: str) -> str:
    """归一化 locator：无 scheme（裸路径）则转为 file:// URI。"""
    if "://" in locator:
        return locator
    return path_to_locator(locator)


class ProjectManager:
    """13 project 命令编排层 + bootstrap 高层方法。

    Args:
        store: ProjectStore（持久化 + 乐观锁）。
        workspace_mgr: WorkspaceManager（register/list_records/get_record）。
        task_mgr: TaskManagerService（经 task_get 命令校验 task 属本 project）。
        cluster_registry: CoreClusterRegistryService（ensure_cluster + get_handle）。
        manifest_store: ManifestStore（实例 manifest 渲染协调，MVP 跳过）。
        on_event: 事件回调（unit 注入）。
        bootstrap_workspace_locator: 首启 bootstrap 用的 workspace locator
            （派生自 config.project.bootstrap_workspace_locator）。
        default_root_locator_template: 未显式传 Root 时使用的模板，支持
            ``{project_id}`` 占位。
    """

    def __init__(
        self,
        store: ProjectStore,
        workspace_mgr: WorkspaceManager,
        task_mgr: TaskManagerService,
        cluster_registry: ClusterRegistryProtocol,
        manifest_store: ManifestStore,
        *,
        on_event: OnEvent | None = None,
        bootstrap_workspace_locator: str = "",
        default_root_locator_template: str = "~/.ghrah/projects/{project_id}",
    ) -> None:
        self._store = store
        self._workspace_mgr = workspace_mgr
        self._task_mgr = task_mgr
        self._cluster_transport = cluster_registry
        self._manifest_store = manifest_store
        self._on_event = on_event
        self._bootstrap_workspace_locator = bootstrap_workspace_locator
        self._default_root_locator_template = default_root_locator_template
        self._create_lock = asyncio.Lock()

    async def handle_command(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = _HANDLERS.get(command)
        if handler is None:
            return _err(f"unknown command: {command}")
        try:
            return await handler(self, payload)
        except ValidationError as e:
            missing = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]
            if missing:
                return _err(f"{missing[0]} required")
            return _err(f"invalid payload: {e}")
        except (ProjectNotFoundError, ConcurrentModificationError) as e:
            return _err(str(e))
        except ValueError as e:
            return _err(str(e))

    # ─── helpers ───

    async def _emit(self, event_type: str, record: ProjectRecord) -> None:
        if self._on_event is None:
            return
        await self._on_event(event_type, {"project": record.to_wire()})

    async def _emit_agent(
        self, event_type: str, record: ProjectRecord, agent: AgentSpec
    ) -> None:
        if self._on_event is None:
            return
        await self._on_event(
            event_type,
            {
                "project": record.to_wire(),
                "agent_name": agent.name,
                "agent_id": agent.agent_id,
            },
        )

    def _root_locator_for(self, project_id: str, requested: str = "") -> str:
        value = requested or self._default_root_locator_template.format(project_id=project_id)
        return canonical_file_locator(value)

    def _validate_agent(self, agent: AgentSpec, project: ProjectRecord) -> None:
        """agent_id project 内唯一 + name cluster 内唯一 + 归属/授权校验。"""
        if agent.cluster_id not in project.cluster_ids:
            raise ValueError(f"agent {agent.name!r} cluster_id {agent.cluster_id!r} not in project")
        for existing in project.agents:
            if agent.agent_id and existing.agent_id == agent.agent_id:
                raise ValueError(f"agent_id {agent.agent_id!r} already exists in project")
            if existing.name == agent.name and existing.cluster_id == agent.cluster_id:
                raise ValueError(
                    f"agent {agent.name!r} already exists in cluster {agent.cluster_id!r}"
                )
        validate_path_grants_non_overlapping(agent, project.workspaces)

    # ─── 命令 handlers ───

    async def _handle_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._create_lock:
            return await self._handle_create_locked(payload)

    async def _handle_create_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectCreatePayload.model_validate(payload)
        if not p.name.strip():
            return _err("name required")
        workspace_inputs = list(p.writable_workspaces)

        normalized_workspaces: list[dict[str, Any]] = []
        for item in workspace_inputs:
            raw = item if isinstance(item, dict) else item.model_dump()
            raw_locator = str(raw["locator"]).strip()
            if not raw_locator:
                return _err("writable_workspaces locator required")
            locator = _normalize_locator(raw_locator)
            normalized_workspaces.append({**raw, "locator": locator})
        defaults = [w for w in normalized_workspaces if w["default_for_agents"]]
        if len(normalized_workspaces) == 1 and not defaults:
            normalized_workspaces[0]["default_for_agents"] = True
        elif len(defaults) > 1 or (len(normalized_workspaces) > 1 and not defaults):
            return _err("writable_workspaces must have exactly one default_for_agents workspace")

        record = make_project_record(
            name=p.name.strip(),
            description=p.description.strip(),
            manifest_ref=p.manifest_ref,
        )
        root_locator = self._root_locator_for(record.project_id, p.project_root_locator)
        project_paths = ProjectPaths.from_locator(root_locator)
        record = record.model_copy(
            update={"project_root_locator": root_locator}
        )
        cluster_id = uuid4().hex
        await self._check_create_paths(
            root_locator, [str(w["locator"]) for w in normalized_workspaces]
        )

        receipt = None
        registered_ids: list[str] = []
        stored = False
        cluster_attempted = False
        try:
            receipt = project_paths.initialize(record.project_id)
            mounts: list[WorkspaceMount] = []
            known_ids = {r.workspace_id for r in self._workspace_mgr.list_records()}
            for item in normalized_workspaces:
                ws = await self._workspace_mgr.register_workspace(
                    str(item["locator"]), name=str(item.get("name") or "default")
                )
                if ws.record.workspace_id not in known_ids:
                    registered_ids.append(ws.record.workspace_id)
                    known_ids.add(ws.record.workspace_id)
                mounts.append(
                    WorkspaceMount(
                        workspace_id=ws.record.workspace_id,
                        role=item.get("role"),
                        default_for_agents=bool(item["default_for_agents"]),
                    )
                )
            WorkspaceMount.validate_single_default(mounts)
            record = record.model_copy(
                update={
                    "cluster_ids": [cluster_id],
                    "workspaces": mounts,
                    "recovery": RecoverySpec(on_restart=RecoveryAction(p.recovery)),
                }
            )
            await self._store.upsert(record)
            stored = True
            cluster_attempted = True
            await self._cluster_transport.ensure_cluster(
                cluster_id, project_root_locator=record.project_root_locator
            )
        except Exception as exc:  # noqa: BLE001 — 创建事务在此统一补偿
            if cluster_attempted:
                try:
                    if self._cluster_transport.has_cluster(cluster_id):
                        await self._cluster_transport.shutdown_cluster(cluster_id)
                except Exception:  # noqa: BLE001
                    logger.warning("create rollback: cluster shutdown failed", exc_info=True)
            if stored:
                try:
                    await self._store.delete_uncommitted(record.project_id)
                except Exception:  # noqa: BLE001
                    logger.warning("create rollback: project delete failed", exc_info=True)
            for workspace_id in reversed(registered_ids):
                try:
                    await self._workspace_mgr.unregister_workspace(workspace_id)
                except Exception:  # noqa: BLE001
                    logger.warning("create rollback: workspace unregister failed", exc_info=True)
            if receipt is not None:
                project_paths.rollback_initialize(receipt)
            return _err(f"project creation failed: {exc}")

        try:
            await self._emit("project_created", record)
        except Exception:  # noqa: BLE001 — 资源已提交，事件失败不反向销毁
            logger.exception("project_created event delivery failed for %s", record.project_id)
        return _ok({"project": record.to_wire()})

    async def _check_create_paths(
        self, root_locator: str, workspace_locators: list[str]
    ) -> None:
        records = await self._store.list()
        existing_roots = [r.project_root_locator for r in records if r.project_root_locator]
        existing_workspaces: list[str] = []
        for project in records:
            for mount in project.workspaces:
                rec = self._workspace_mgr.get_record(mount.workspace_id)
                if rec is not None:
                    existing_workspaces.append(rec.locator)
        validate_workspace_locators_non_nested(existing_workspaces + workspace_locators)
        validate_project_path_boundaries(
            root_locator=root_locator,
            existing_root_locators=existing_roots,
            workspace_locators=existing_workspaces + workspace_locators,
        )

    async def migrate_legacy_project_roots(self) -> int:
        """为尚无 Root 的旧 Project 幂等建立内部目录并更新元数据。"""
        async with self._create_lock:
            records = await self._store.list(include_deleted=True)
            migrated = 0
            existing_roots = [r.project_root_locator for r in records if r.project_root_locator]
            workspace_locators: list[str] = []
            for project in records:
                for mount in project.workspaces:
                    workspace = self._workspace_mgr.get_record(mount.workspace_id)
                    if workspace is not None:
                        workspace_locators.append(workspace.locator)
            for record in records:
                if record.project_root_locator:
                    continue
                root_locator = self._root_locator_for(record.project_id)
                validate_project_path_boundaries(
                    root_locator=root_locator,
                    existing_root_locators=existing_roots,
                    workspace_locators=workspace_locators,
                )
                paths = ProjectPaths.from_locator(root_locator)
                receipt = paths.initialize(record.project_id)
                try:
                    await self._store.update(
                        record.project_id,
                        record.version,
                        lambda current: current.model_copy(
                            update={"project_root_locator": root_locator}
                        ),
                    )
                except Exception:
                    paths.rollback_initialize(receipt)
                    raise
                existing_roots.append(root_locator)
                migrated += 1
            return migrated

    async def _handle_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectUpdatePayload.model_validate(payload)
        existing = await self._store.get(p.project_id)
        if existing is None:
            return _err(f"project not found: {p.project_id}")
        expected = p.expected_version if p.expected_version is not None else existing.version

        def mutator(r: ProjectRecord) -> ProjectRecord:
            updates: dict[str, Any] = {}
            if p.name is not None:
                updates["name"] = p.name
            if p.description is not None:
                updates["description"] = p.description
            if p.manifest_ref is not None:
                updates["manifest_ref"] = p.manifest_ref
            return r.model_copy(update=updates)

        updated = await self._store.update(p.project_id, expected, mutator)
        await self._emit("project_updated", updated)
        return _ok({"project": updated.to_wire()})

    async def _handle_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectIdPayload.model_validate(payload)
        record = await self._store.get(p.project_id)
        if record is None:
            return _err(f"project not found: {p.project_id}")
        return _ok({"project": record.to_wire()})

    async def _handle_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectListPayload.model_validate(payload)
        records = await self._store.list(status=p.status, include_deleted=p.include_deleted)
        return _ok(
            {
                "projects": [r.to_wire() for r in records],
                "count": len(records),
            }
        )

    async def _handle_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectDeletePayload.model_validate(payload)
        existing = await self._store.get(p.project_id, include_deleted=True)
        if existing is None:
            return _err(f"project not found: {p.project_id}")
        paths: ProjectPaths | None = None
        if p.purge_storage:
            try:
                paths = ProjectPaths.from_locator(existing.project_root_locator)
                paths.validate_owner(existing.project_id)
            except (OSError, ValueError) as exc:
                return _err(str(exc))
        # shutdown 全部 cluster + 关 transport
        for cluster_id in existing.cluster_ids:
            try:
                if self._cluster_transport.has_cluster(cluster_id):
                    await self._cluster_transport.shutdown_cluster(cluster_id)
            except Exception:  # noqa: BLE001
                logger.warning("delete: shutdown cluster %s failed", cluster_id)
        await self._store.soft_delete(existing.project_id, existing.version)
        if paths is not None:
            paths.purge(existing.project_id)
        await self._emit("project_deleted", existing)
        return _ok(
            {
                "project_id": p.project_id,
                "deleted": True,
                "storage_purged": paths is not None,
            }
        )

    async def _handle_add_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectAddAgentPayload.model_validate(payload)
        existing = await self._store.get(p.project_id)
        if existing is None:
            return _err(f"project not found: {p.project_id}")
        expected = p.expected_version if p.expected_version is not None else existing.version
        agent = AgentSpec(
            name=p.agent.name,
            cluster_id=p.agent.cluster_id,
            agent_id=p.agent.agent_id or uuid4().hex,
            manifest_ref=p.agent.manifest_ref,
            instance_manifest_path=(
                p.agent.instance_manifest_path
                or str(
                    ProjectPaths.from_locator(existing.project_root_locator).agent_manifest_dir
                    / f"{p.agent.name}.yaml"
                )
            ),
            system_prompt=p.agent.system_prompt,
            abilities=p.agent.abilities,
            path_grants=[
                PathGrant(workspace_id=g.workspace_id, subpath=g.subpath)
                for g in p.agent.path_grants
            ],
        )
        self._validate_agent(agent, existing)

        def mutator(r: ProjectRecord) -> ProjectRecord:
            return r.model_copy(update={"agents": [*r.agents, agent]})

        updated = await self._store.update(p.project_id, expected, mutator)
        # active 且 cluster 缺该 agent 则 spawn
        if updated.status == ProjectStatus.ACTIVE:
            await self._ensure_agent_spawned(agent, updated.project_root_locator)
        await self._emit_agent("project_agent_added", updated, agent)
        return _ok(
            {
                "project": updated.to_wire(),
                "agent_name": agent.name,
                "agent_id": agent.agent_id,
            }
        )

    async def _ensure_agent_spawned(self, agent: AgentSpec, project_root_locator: str) -> None:
        """若 cluster 缺该 agent 则 spawn（MVP：不预检 list，直接 spawn，幂等由 Core 保证）。"""
        try:
            handle = await self._cluster_transport.ensure_cluster(
                agent.cluster_id, project_root_locator=project_root_locator
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("add_agent: ensure_cluster %s failed: %s", agent.cluster_id, exc)
            return
        spawn_payload = SpawnAgentPayload(
            config=AgentConfigPayload(
                name=agent.name,
                agent_id=agent.agent_id,
                system_prompt=agent.system_prompt or "",
            ),
            abilities=None,
            manifest_ref=agent.manifest_ref or None,
        )
        try:
            result = await handle.spawn_agent(spawn_payload)
            if not result.get("success"):
                logger.warning("add_agent: spawn %s rejected: %s", agent.name, result.get("error"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("add_agent: spawn %s failed: %s", agent.name, exc)

    async def _handle_remove_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectRemoveAgentPayload.model_validate(payload)
        existing = await self._store.get(p.project_id)
        if existing is None:
            return _err(f"project not found: {p.project_id}")
        expected = p.expected_version if p.expected_version is not None else existing.version
        target = next(
            (
                a
                for a in existing.agents
                if (p.agent_id and a.agent_id == p.agent_id)
                or (not p.agent_id and a.name == p.agent_name)
            ),
            None,
        )
        if target is None:
            identity = p.agent_id or p.agent_name
            return _err(f"agent not found: {identity}")

        def mutator(r: ProjectRecord) -> ProjectRecord:
            def is_target(candidate: AgentSpec) -> bool:
                if target.agent_id:
                    return candidate.agent_id == target.agent_id
                return (
                    candidate.name == target.name
                    and candidate.cluster_id == target.cluster_id
                )

            return r.model_copy(
                update={"agents": [a for a in r.agents if not is_target(a)]}
            )

        updated = await self._store.update(p.project_id, expected, mutator)
        # terminate agent
        if self._cluster_transport.has_cluster(target.cluster_id):
            try:
                handle = self._cluster_transport.get_handle(target.cluster_id)
                await handle.terminate_agent(target.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("remove_agent: terminate %s failed: %s", p.agent_name, exc)
        await self._emit_agent("project_agent_removed", updated, target)
        return _ok(
            {
                "project": updated.to_wire(),
                "agent_name": target.name,
                "agent_id": target.agent_id,
            }
        )

    async def _handle_link_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._toggle_task_link(payload, link=True)

    async def _handle_unlink_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._toggle_task_link(payload, link=False)

    async def _toggle_task_link(self, payload: dict[str, Any], *, link: bool) -> dict[str, Any]:
        # 两种 payload 结构相同（project_id/task_id/expected_version）；各自 validate
        # 以校验入参，随后统一读 dict 字段避免 union 赋值类型冲突。
        if link:
            ProjectLinkTaskPayload.model_validate(payload)
        else:
            ProjectUnlinkTaskPayload.model_validate(payload)
        project_id = payload["project_id"]
        task_id = payload["task_id"]
        expected_version = payload.get("expected_version")
        existing = await self._store.get(project_id)
        if existing is None:
            return _err(f"project not found: {project_id}")
        exp = expected_version if expected_version is not None else existing.version
        # 校验 task 存在（经 task_get 命令）
        task_result = await self._task_mgr.handle_command("task_get", {"task_id": task_id})
        if not task_result.get("success"):
            return _err(f"task not found: {task_id}")

        def mutator(r: ProjectRecord) -> ProjectRecord:
            task_ids = list(r.task_ids)
            if link:
                if task_id not in task_ids:
                    task_ids.append(task_id)
            else:
                task_ids = [t for t in task_ids if t != task_id]
            return r.model_copy(update={"task_ids": task_ids})

        updated = await self._store.update(project_id, exp, mutator)
        return _ok({"project": updated.to_wire(), "task_id": task_id})

    async def _handle_set_recovery(self, payload: dict[str, Any]) -> dict[str, Any]:
        p = ProjectSetRecoveryPayload.model_validate(payload)
        existing = await self._store.get(p.project_id)
        if existing is None:
            return _err(f"project not found: {p.project_id}")
        expected = p.expected_version if p.expected_version is not None else existing.version

        def mutator(r: ProjectRecord) -> ProjectRecord:
            return r.model_copy(update={"recovery": RecoverySpec(on_restart=p.recovery)})

        updated = await self._store.update(p.project_id, expected, mutator)
        await self._emit("project_recovery_set", updated)
        return _ok({"project": updated.to_wire()})

    async def _handle_pause(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._transition_status(
            payload,
            ProjectStatus.PAUSED,
            "project_paused",
            shutdown_clusters=True,
        )

    async def _handle_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._transition_status(
            payload, ProjectStatus.ACTIVE, "project_resumed", reinit_clusters=True
        )

    async def _handle_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._transition_status(
            payload, ProjectStatus.STOPPED, "project_stopped", shutdown_clusters=True
        )

    async def _transition_status(
        self,
        payload: dict[str, Any],
        target: ProjectStatus,
        event_type: str,
        *,
        shutdown_clusters: bool = False,
        reinit_clusters: bool = False,
    ) -> dict[str, Any]:
        p = ProjectIdPayload.model_validate(payload)
        existing = await self._store.get(p.project_id)
        if existing is None:
            return _err(f"project not found: {p.project_id}")
        if not can_transition(existing.status, target):
            return _err(f"illegal transition: {existing.status.value} -> {target.value}")
        updated = await self._store.update(
            p.project_id, existing.version, lambda r: r.model_copy(update={"status": target})
        )
        if shutdown_clusters:
            for cluster_id in existing.cluster_ids:
                try:
                    if self._cluster_transport.has_cluster(cluster_id):
                        await self._cluster_transport.shutdown_cluster(cluster_id)
                except Exception:  # noqa: BLE001
                    logger.warning("status: shutdown cluster %s failed", cluster_id)
        if reinit_clusters:
            for cluster_id in existing.cluster_ids:
                try:
                    await self._cluster_transport.ensure_cluster(
                        cluster_id,
                        project_root_locator=existing.project_root_locator,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("status: reinit cluster %s failed: %s", cluster_id, exc)
        await self._emit(event_type, updated)
        return _ok({"project": updated.to_wire()})

    # ─── bootstrap 高层方法（决策 2，供 S4.6 reconcile） ───

    async def bootstrap_default_project(self) -> ProjectRecord:
        async with self._create_lock:
            return await self._bootstrap_default_project_locked()

    async def _bootstrap_default_project_locked(self) -> ProjectRecord:
        """建 default project（1 default cluster + 1 default workspace + init_cluster）。"""
        locator = self._bootstrap_workspace_locator
        if not locator:
            raise ValueError("bootstrap_workspace_locator not configured")
        locator = _normalize_locator(locator)
        record = make_project_record(name="default")
        root_locator = self._root_locator_for(record.project_id)
        project_paths = ProjectPaths.from_locator(root_locator)
        record = record.model_copy(
            update={"project_root_locator": root_locator}
        )
        cluster_id = "default"
        await self._check_create_paths(root_locator, [locator])
        receipt = None
        registered_id: str | None = None
        stored = False
        cluster_attempted = False
        try:
            receipt = project_paths.initialize(record.project_id)
            known_ids = {r.workspace_id for r in self._workspace_mgr.list_records()}
            ws = await self._workspace_mgr.register_workspace(locator, name="default")
            if ws.record.workspace_id not in known_ids:
                registered_id = ws.record.workspace_id
            mount = WorkspaceMount(
                workspace_id=ws.record.workspace_id,
                role="default",
                default_for_agents=True,
            )
            record = record.model_copy(
                update={"cluster_ids": [cluster_id], "workspaces": [mount]}
            )
            await self._store.upsert(record)
            stored = True
            cluster_attempted = True
            await self._cluster_transport.ensure_cluster(
                cluster_id, project_root_locator=record.project_root_locator
            )
        except Exception:
            if cluster_attempted:
                try:
                    if self._cluster_transport.has_cluster(cluster_id):
                        await self._cluster_transport.shutdown_cluster(cluster_id)
                except Exception:  # noqa: BLE001
                    logger.warning("bootstrap rollback: cluster shutdown failed", exc_info=True)
            if stored:
                try:
                    await self._store.delete_uncommitted(record.project_id)
                except Exception:  # noqa: BLE001
                    logger.warning("bootstrap rollback: project delete failed", exc_info=True)
            if registered_id is not None:
                try:
                    await self._workspace_mgr.unregister_workspace(registered_id)
                except Exception:  # noqa: BLE001
                    logger.warning("bootstrap rollback: workspace unregister failed", exc_info=True)
            if receipt is not None:
                project_paths.rollback_initialize(receipt)
            raise
        try:
            await self._emit("project_created", record)
        except Exception:  # noqa: BLE001
            logger.exception("bootstrap project_created event delivery failed")
        return record

    async def adopt_existing_agents(self, project_id: str, cluster_id: str) -> list[AgentSpec]:
        """经 ClusterHandle.list_agents 从 Core 取现有 agent，构造 AgentSpec 并加入 project。"""
        existing = await self._store.get(project_id)
        if existing is None:
            raise ProjectNotFoundError(f"project not found: {project_id}")
        handle = await self._cluster_transport.ensure_cluster(
            cluster_id, project_root_locator=existing.project_root_locator
        )
        agents_info: list[dict[str, Any]] = []
        try:
            agents_info = await handle.list_agents()
        except Exception as exc:  # noqa: BLE001
            logger.warning("adopt_existing_agents: list_agents failed: %s", exc)
            return []
        specs: list[AgentSpec] = []
        for info in agents_info:
            name = info.get("name")
            if not isinstance(name, str) or not name:
                continue
            spec = AgentSpec(
                name=name,
                cluster_id=cluster_id,
                agent_id=(
                    str(info.get("agent_id")) if info.get("agent_id") else uuid4().hex
                ),
                manifest_ref="",
                instance_manifest_path="",
            )
            specs.append(spec)

        def mutator(r: ProjectRecord) -> ProjectRecord:
            # 去重：已有同名（同 cluster）不重复加入
            existing_names = {(a.name, a.cluster_id) for a in r.agents}
            new_agents = [s for s in specs if (s.name, s.cluster_id) not in existing_names]
            return r.model_copy(update={"agents": [*r.agents, *new_agents]})

        await self._store.update(project_id, existing.version, mutator)
        if self._on_event is not None and specs:
            updated = await self._store.get(project_id)
            if updated is not None:
                await self._emit("project_updated", updated)
        return specs


_HANDLERS: dict[str, Callable[[ProjectManager, dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    "project_create": ProjectManager._handle_create,
    "project_update": ProjectManager._handle_update,
    "project_get": ProjectManager._handle_get,
    "project_list": ProjectManager._handle_list,
    "project_delete": ProjectManager._handle_delete,
    "project_add_agent": ProjectManager._handle_add_agent,
    "project_remove_agent": ProjectManager._handle_remove_agent,
    "project_link_task": ProjectManager._handle_link_task,
    "project_unlink_task": ProjectManager._handle_unlink_task,
    "project_set_recovery": ProjectManager._handle_set_recovery,
    "project_pause": ProjectManager._handle_pause,
    "project_resume": ProjectManager._handle_resume,
    "project_stop": ProjectManager._handle_stop,
}
