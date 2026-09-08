# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""WorkspaceManager：workspace 挂载语义管理器（登记 + 授权 + 解挂）。

- ``AgentWorkspace``：WorkspaceRecord + provider 的运行时包装。
- ``WorkspaceManager``：workspace_id 键控 + ProviderRegistry + WorkspaceStore，
  ``start()`` 时从 store 重建内存索引，并把 store 未就绪期间内存登记的记录
  回填 store（store 是唯一注册真相，无 marker 落盘）。

挂载语义契约：

- ``register_workspace``：登记已有目录，零物理操作（不 git init、不写
  config、不 add/commit、不落 marker）；目录内容/``.git`` 状态一律不探测
  不修改，仅做存在性检查（fail-closed）。git provider 类型显式拒绝。
- ``create_workspace``：ghrah 新建默认目录（``<root>/<agent_name>``、plain），
  仅此路径允许 mkdir。
- ``destroy_workspace`` ≡ ``unregister_workspace``：store 软删 + sandbox
  external root 授权解除，**永不物理删除目录**（rmtree 全域退出）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ghrah.subject.workspace import (
    PlainWorkspaceProvider,
    ProviderRegistry,
    SnapshotError,
    WorkspaceProviderError,
    WorkspaceRecord,
    WorkspaceStore,
    build_default_registry,
    locator_to_path,
    path_to_locator,
)
from ghrah.subject.workspace.models import WorkspaceStatus
from ghrah.subject.workspace.providers.base import WorkspaceProvider

if TYPE_CHECKING:
    from ghrah.subject.sandbox.executor import SandboxExecutor

__all__ = [
    "WorkspaceManager",
    "AgentWorkspace",
    "WorkspaceStatus",
    "SnapshotError",
]

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkspace:
    """单个 Agent 的 workspace（挂载登记运行时包装）。

    包装 :class:`WorkspaceRecord` + provider，保留 .name/.path/.sandbox 旧字段。
    """

    name: str
    path: str
    sandbox: SandboxExecutor = field(repr=False)
    record: WorkspaceRecord = field(repr=False)
    provider: WorkspaceProvider = field(repr=False)

    async def status(self) -> WorkspaceStatus:
        return await self.provider.status(self.record)


class WorkspaceManager:
    """Agent workspace 管理器（挂载语义：登记 + 授权 + 解挂）。

    持有 WorkspaceStore + ProviderRegistry。``start()`` 时：
    1. 启动 store（若 db_path 提供），加载全部未软删记录重建内存索引；
    2. 把 store 未就绪期间仅内存登记的记录回填 store。

    agent_name 兼容桥：``create_workspace(agent_name)`` 映射为该 agent 的默认
    workspace（``<root>/<agent_name>``、plain 类型、首次访问惰性创建并登记）。
    store 未就绪时降级为「仅 mkdir + 内存登记」，待 ``start()`` 时回填 store。
    """

    def __init__(
        self,
        root_path: str,
        sandbox: SandboxExecutor | None = None,
        owns_sandbox: bool = True,
        db_path: str | None = None,
        subject_id: str = "default",
    ) -> None:
        self._root_path = os.path.abspath(root_path)
        self.sandbox = sandbox
        self._owns_sandbox = owns_sandbox
        self._subject_id = subject_id
        # workspace_id → AgentWorkspace
        self._by_id: dict[str, AgentWorkspace] = {}
        # agent_name → workspace_id（兼容桥索引）
        self._by_agent: dict[str, str] = {}
        self._registry: ProviderRegistry | None = None
        self._store: WorkspaceStore | None = None
        self._db_path = db_path
        self._started = False

    async def start(self) -> None:
        os.makedirs(self._root_path, exist_ok=True)
        if self.sandbox and self._owns_sandbox:
            await self.sandbox.start()
        if self.sandbox is not None and self._registry is None:
            self._registry = build_default_registry(self.sandbox)
        if self._db_path is not None and self._store is None:
            self._store = WorkspaceStore(self._db_path)
            await self._store.start()
        self._started = True
        # 重建内存索引：先从 store 加载，再把 store 未就绪期间内存登记的回填
        await self._reload_from_store()
        await self._backfill_store_from_memory()

    async def stop(self) -> None:
        self._by_id.clear()
        self._by_agent.clear()
        self._started = False
        if self._store is not None:
            await self._store.stop()
            self._store = None
        if self.sandbox and self._owns_sandbox:
            await self.sandbox.stop()

    @property
    def root_path(self) -> str:
        return self._root_path

    @property
    def registry(self) -> ProviderRegistry | None:
        return self._registry

    # ─── 内部：内存索引 / store 一致性 ───

    async def _reload_from_store(self) -> None:
        """从 store 加载全部未软删记录重建内存索引。

        未知 provider_type 的记录跳过 + warning（启动容错，不崩溃）；
        该 workspace 的后续操作会在取 provider 时 fail-closed 报错。
        """
        if self._store is None:
            return
        records = await self._store.list_all_active()
        for record in records:
            provider = self._lookup_provider(record.provider_type)
            if provider is None:
                continue
            self._index_record(record, provider)

    async def _backfill_store_from_memory(self) -> None:
        """把 store 未就绪期间仅内存登记的记录回填 store（无 marker 后的补登路径）。

        locator UNIQUE 冲突（另一记录已占用）容忍并 warning，不中断启动。
        """
        if self._store is None:
            return
        for workspace in list(self._by_id.values()):
            record = workspace.record
            existing = await self._store.get(record.workspace_id)
            if existing is not None:
                continue
            try:
                await self._store.upsert(record)
                logger.info(
                    "Backfilled workspace %s (%s) into store",
                    record.workspace_id,
                    record.locator,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Workspace store backfill failed for %s",
                    record.workspace_id,
                    exc_info=True,
                )

    def _lookup_provider(self, provider_type: str) -> WorkspaceProvider | None:
        """按 provider_type 从 registry 取 provider；未注册返回 None。"""
        if self._registry is None:
            return None
        if not self._registry.has(provider_type):
            logger.warning(
                "Unknown workspace provider_type %r for record lookup; skipped",
                provider_type,
            )
            return None
        return self._registry.get(provider_type)

    def _index_record(self, record: WorkspaceRecord, provider: WorkspaceProvider) -> None:
        if record.workspace_id in self._by_id:
            return
        ws_path = locator_to_path(record.locator)
        if self.sandbox is not None:
            self.sandbox.allow_external_workspace(ws_path)
        workspace = AgentWorkspace(
            name=record.name,
            path=ws_path,
            sandbox=self.sandbox,
            record=record,
            provider=provider,
        )
        self._by_id[record.workspace_id] = workspace
        # agent_name 索引：默认 workspace 命名约定 <root>/<agent_name>
        self._by_agent[record.name] = record.workspace_id

    async def _persist(self, record: WorkspaceRecord) -> None:
        if self._store is not None:
            try:
                await self._store.upsert(record)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Workspace store upsert failed for %s",
                    record.workspace_id,
                    exc_info=True,
                )

    # ─── agent_name 兼容桥 ───

    async def create_workspace(self, agent_name: str) -> AgentWorkspace:
        """为 agent 创建默认 workspace（``<root>/<agent_name>``、plain）。

        幂等：已登记则返回现有。仅此路径允许 mkdir（ghrah 新建目录）。
        store 未就绪时降级为「仅 mkdir + 内存登记」，待 ``start()`` 时回填 store。
        """
        existing_id = self._by_agent.get(agent_name)
        if existing_id is not None and existing_id in self._by_id:
            return self._by_id[existing_id]

        if self.sandbox is None:
            raise WorkspaceProviderError("SandboxExecutor is required for workspace operations")

        ws_path = os.path.join(self._root_path, agent_name)
        record = WorkspaceRecord(
            name=agent_name,
            provider_type="plain",
            subject_id=self._subject_id,
            locator=path_to_locator(ws_path),
        )
        provider = PlainWorkspaceProvider()
        try:
            await provider.init(record)
        except WorkspaceProviderError as exc:
            raise WorkspaceProviderError(str(exc)) from exc

        workspace = AgentWorkspace(
            name=agent_name,
            path=ws_path,
            sandbox=self.sandbox,
            record=record,
            provider=provider,
        )
        self._by_id[record.workspace_id] = workspace
        self._by_agent[agent_name] = record.workspace_id

        # store 就绪则补登；未就绪降级（待 start() 回填）
        if self._started and self._store is not None:
            await self._persist(record)

        logger.info("Created workspace for agent '%s' at %s", agent_name, ws_path)
        return workspace

    async def destroy_workspace(self, agent_name: str) -> None:
        """解挂该 agent 的默认 workspace（永不物理删除目录）。

        等价于 :meth:`unregister_workspace`：store 软删 + sandbox 授权解除。
        """
        workspace_id = self._by_agent.get(agent_name)
        if workspace_id is None:
            return
        await self.unregister_workspace(workspace_id)

    async def unregister_workspace(self, workspace_id: str) -> None:
        """移除注册关系但保留物理目录（永不 rmtree）。

        供 Project 创建失败安全补偿与 destroy_workspace 共用。
        """
        workspace = self._by_id.pop(workspace_id, None)
        if workspace is None:
            return
        if self.sandbox is not None:
            self.sandbox.disallow_external_workspace(workspace.path)
        stale_names = [name for name, wid in self._by_agent.items() if wid == workspace_id]
        for name in stale_names:
            self._by_agent.pop(name, None)
        if self._store is not None:
            try:
                await self._store.soft_delete(workspace_id)
            except Exception:  # noqa: BLE001
                logger.warning("Soft-delete failed for %s", workspace_id, exc_info=True)
        logger.info(
            "Unregistered workspace %s (%s); directory preserved",
            workspace_id,
            workspace.record.locator,
        )

    def get_workspace(self, agent_name: str) -> AgentWorkspace | None:
        workspace_id = self._by_agent.get(agent_name)
        if workspace_id is None:
            return None
        return self._by_id.get(workspace_id)

    def list_workspaces(self) -> list[str]:
        return list(self._by_agent.keys())

    # ─── workspace_id 一等接口 ───

    def get_workspace_by_id(self, workspace_id: str) -> AgentWorkspace | None:
        return self._by_id.get(workspace_id)

    def get_record(self, workspace_id: str) -> WorkspaceRecord | None:
        ws = self._by_id.get(workspace_id)
        return ws.record if ws is not None else None

    def list_records(self) -> list[WorkspaceRecord]:
        return [ws.record for ws in self._by_id.values()]

    def list_records_by_provider(self, provider_type: str | None = None) -> list[WorkspaceRecord]:
        """按 provider_type 过滤记录（None 表示全部）。"""
        records = self.list_records()
        if provider_type is None:
            return records
        return [r for r in records if r.provider_type == provider_type]

    async def register_workspace(
        self, locator: str, *, name: str = "", provider_type: str | None = None
    ) -> AgentWorkspace:
        """把已有目录登记为 workspace（workspace_register 命令后端）。

        挂载语义：仅登记 + 授权，对目录零物理操作——不 git init、不写
        config、不 add/commit、不落 marker；目录内容/``.git`` 状态一律不探测
        不修改。

        Args:
            locator: file:// URI（裸路径自动归一）。
            name: 人类可读名，默认从路径末段推断。
            provider_type: 显式 provider 类型；``"git"`` 一律拒绝（fail-closed，
                legacy GitWorkspaceProvider 已移除），None 由 registry.detect
                分派（当前恒 plain）。

        Raises:
            WorkspaceProviderError: locator 非法、目录不存在、provider 类型
                不受支持或 provider_type 为 "git"。
        """
        if self._registry is None:
            raise WorkspaceProviderError(
                "WorkspaceManager not started: registry unavailable for register_workspace"
            )
        if provider_type == "git":
            raise WorkspaceProviderError(
                "git workspace provider is no longer supported; "
                "workspaces are registered by mounting (read/write authorization) "
                "with zero physical writes — use the default plain provider. "
                "See plans/planning/2026-09-08-dogfood-prereq-fix.md §A2/A3 "
                "(shadow-git checkpoint backlog) for the migration notes."
            )
        try:
            ws_path = locator_to_path(locator)
        except ValueError as exc:
            raise WorkspaceProviderError(str(exc)) from exc
        # fail-closed：只做存在性检查，不创建、不探测内容
        if not os.path.isdir(ws_path):
            raise WorkspaceProviderError(f"workspace directory does not exist: {ws_path}")

        if provider_type is not None:
            if not self._registry.has(provider_type):
                raise WorkspaceProviderError(f"Unknown workspace provider type: {provider_type!r}")
            provider = self._registry.get(provider_type)
        else:
            provider = self._registry.detect(locator)
            if provider is None:
                raise WorkspaceProviderError(f"Cannot detect provider for locator: {locator}")

        # 幂等去重：同 locator 已登记（store 或内存）则返回现有
        if self._store is not None:
            existing_record = await self._store.get_by_locator(locator)
            if existing_record is not None:
                existing = self._by_id.get(existing_record.workspace_id)
                if existing is not None:
                    return existing
        for ws in self._by_id.values():
            if ws.record.locator == locator:
                return ws

        record = WorkspaceRecord(
            name=name or os.path.basename(ws_path),
            provider_type=provider.provider_type,
            subject_id=self._subject_id,
            locator=locator,
        )
        self._index_record(record, provider)
        if self._store is not None:
            await self._persist(record)
        logger.info("Registered workspace %s (%s)", record.workspace_id, locator)
        return self._by_id[record.workspace_id]
