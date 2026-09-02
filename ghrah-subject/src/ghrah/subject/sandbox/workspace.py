# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""兼容 re-export 层 + WorkspaceManager 重构（W5）。

- ``AgentWorkspace`` / ``WorkspaceStatus`` / ``SnapshotError`` / ``SnapshotInfo``
  保留旧 API 表面作为兼容桥，实际 git 实现平移至 GitWorkspaceProvider。
- ``WorkspaceManager`` 重构为 workspace_id 键控 + ProviderRegistry + WorkspaceStore
  + start 时加载 store 重建内存索引 + orphan adopt 扫描 + agent_name 兼容桥。

桥的 store 生命周期契约（§四 W5）：
当 store 未就绪（Manager 未 ``start()``，或未传 db_path 即无持久化）时，
``create_workspace(agent_name)`` 降级为「仅 init + 内存登记」，待 ``start()`` 时
由 orphan adopt 扫描补登 store（marker 已落盘，adopt 可重建 record）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ghrah.subject.workspace import (
    GitWorkspaceProvider,
    ProviderRegistry,
    SnapshotError,
    WorkspaceProviderError,
    WorkspaceRecord,
    WorkspaceStore,
    build_default_registry,
    locator_to_path,
    path_to_locator,
)
from ghrah.subject.workspace import (
    SnapshotInfo as _NewSnapshotInfo,
)
from ghrah.subject.workspace.marker import MARKER_FILENAME
from ghrah.subject.workspace.providers.base import VersionedWorkspaceProvider

if TYPE_CHECKING:
    from ghrah.subject.sandbox.executor import SandboxExecutor

__all__ = [
    "WorkspaceManager",
    "AgentWorkspace",
    "WorkspaceStatus",
    "SnapshotInfo",
    "SnapshotError",
]

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceStatus:
    """工作区 Git 状态（兼容旧形态）。

    由 :meth:`AgentWorkspace.status` 从 provider 通用 status 的 extra 映射而来，
    保留 branch/is_clean/staged_files/unstaged_files/untracked_files 字段以维持
    现有调用方与测试零改动。
    """

    branch: str
    is_clean: bool
    staged_files: list[str]
    unstaged_files: list[str]
    untracked_files: list[str]


# 兼容旧导入名（指向新包的 pydantic SnapshotInfo）。
SnapshotInfo = _NewSnapshotInfo


@dataclass
class AgentWorkspace:
    """单个 Agent 的工作区（兼容桥）。

    包装 :class:`WorkspaceRecord` + provider，方法委托至 provider，保留
    .name/.path/.sandbox 旧字段。
    """

    name: str
    path: str
    sandbox: SandboxExecutor = field(repr=False)
    record: WorkspaceRecord = field(repr=False)
    provider: VersionedWorkspaceProvider = field(repr=False)

    async def snapshot(self, message: str = "") -> str:
        return await self.provider.snapshot(self.record, message=message)

    async def diff(self, snapshot_id: str | None = None) -> str:
        return await self.provider.diff(self.record, snapshot_id=snapshot_id)

    async def rollback(self, snapshot_id: str) -> None:
        await self.provider.rollback(self.record, snapshot_id)

    async def status(self) -> WorkspaceStatus:
        ws_status = await self.provider.status(self.record)
        extra = ws_status.extra
        return WorkspaceStatus(
            branch=str(extra.get("branch", "main")),
            is_clean=bool(extra.get("is_clean", True)),
            staged_files=list(extra.get("staged_files", [])),
            unstaged_files=list(extra.get("unstaged_files", [])),
            untracked_files=list(extra.get("untracked_files", [])),
        )

    async def list_snapshots(self, max_count: int = 50) -> list[SnapshotInfo]:
        return await self.provider.list_snapshots(self.record, max_count=max_count)


class WorkspaceManager:
    """Agent 工作区管理器（workspace_id 键控 + 兼容桥）。

    持有 WorkspaceStore + ProviderRegistry。``start()`` 时：
    1. 启动 store（若 db_path 提供），加载全部未软删记录重建内存索引；
    2. 扫描 root_path 子目录做一次 orphan adopt（经 registry.detect + provider.adopt），
       将有 marker 未注册的目录补登 store + 内存索引。

    agent_name 兼容桥：``create_workspace(agent_name)`` 映射为该 agent 的默认
    workspace（``<root>/<agent_name>``、git 类型、首次访问惰性创建并登记 store）。
    store 未就绪时降级为「仅 init + 内存登记」（marker 已落盘，待 start adopt 补登）。
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
        # 重建内存索引：先从 store 加载，再 orphan adopt 扫描补登
        await self._reload_from_store()
        await self._scan_orphan_adopt()

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
        if self._store is None:
            return
        records = await self._store.list_all_active()
        for record in records:
            self._index_record(record)

    async def _scan_orphan_adopt(self) -> None:
        """扫描 root_path 子目录，认领有 marker 未注册的目录，补登 store + 内存。

        轻量：仅扫一层子目录。无 marker / 旧格式 / provider_type 不匹配 → 跳过。
        已注册（store 命中或内存已存在同 workspace_id/locator）→ 跳过。
        """
        if self._registry is None or not os.path.isdir(self._root_path):
            return
        seen_ids = set(self._by_id.keys())
        seen_locators = {r.locator for r in (await self._all_records_in_memory())}
        try:
            entries = os.listdir(self._root_path)
        except OSError:
            return
        for entry in entries:
            sub = os.path.join(self._root_path, entry)
            if not os.path.isdir(sub):
                continue
            locator = path_to_locator(sub)
            if locator in seen_locators:
                continue
            provider = self._registry.detect(locator)
            if provider is None:
                continue
            try:
                result = await provider.adopt(locator)
            except Exception:  # noqa: BLE001 — 扫描不因单个目录异常中断
                logger.warning("Orphan adopt failed for %s", locator, exc_info=True)
                continue
            if result is None:
                continue
            # marker subject_id 必须匹配本 subject（防误认领其他 subject 目录）
            if result.subject_id != self._subject_id:
                logger.info(
                    "Skipping orphan %s: subject_id mismatch (%s != %s)",
                    locator,
                    result.subject_id,
                    self._subject_id,
                )
                continue
            if result.workspace_id in seen_ids:
                continue
            record = self._build_record_from_adopt(result, sub)
            self._index_record(record)
            if self._store is not None:
                try:
                    await self._store.upsert(record)
                    logger.info("Orphan adopted into store: %s (%s)", record.workspace_id, locator)
                except Exception:  # noqa: BLE001
                    logger.warning("Orphan upsert failed for %s", locator, exc_info=True)
            seen_ids.add(record.workspace_id)
            seen_locators.add(record.locator)

    async def _all_records_in_memory(self) -> list[WorkspaceRecord]:
        return [ws.record for ws in self._by_id.values()]

    def _build_record_from_adopt(self, result: object, dir_path: str) -> WorkspaceRecord:
        from ghrah.subject.workspace.models import AdoptResult

        assert isinstance(result, AdoptResult)
        return WorkspaceRecord(
            workspace_id=result.workspace_id,
            name=result.name or os.path.basename(dir_path),
            provider_type=result.provider_type,
            subject_id=result.subject_id,
            locator=path_to_locator(dir_path),
        )

    def _index_record(self, record: WorkspaceRecord) -> None:
        if record.workspace_id in self._by_id:
            return
        provider = self._provider_for(record)
        ws_path = locator_to_path(record.locator)
        if self.sandbox is not None:
            self.sandbox.allow_external_workspace(ws_path)
        workspace = AgentWorkspace(
            name=record.name,
            path=ws_path,
            sandbox=self.sandbox,  # type: ignore[arg-type]
            record=record,
            provider=provider,
        )
        self._by_id[record.workspace_id] = workspace
        # agent_name 索引：默认 workspace 命名约定 <root>/<agent_name>
        self._by_agent[record.name] = record.workspace_id

    def _provider_for(self, record: WorkspaceRecord) -> VersionedWorkspaceProvider:
        """按 provider_type 从 registry 取 provider；缺则回退 git（兼容桥默认）。"""
        if self._registry is not None:
            provider = (
                self._registry.get(record.provider_type)
                if self._registry.has(record.provider_type)
                else None
            )
            if provider is not None and isinstance(provider, VersionedWorkspaceProvider):
                return provider
        # 兼容桥默认：未配 registry 或非版本 provider 时回退 GitWorkspaceProvider
        assert self.sandbox is not None
        return GitWorkspaceProvider(self.sandbox)

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
        """为 agent 创建默认 workspace（``<root>/<agent_name>``、git）。

        幂等：已登记则返回现有。store 未就绪时降级为「仅 init + 内存登记」
        （marker 已落盘，待 start 时 orphan adopt 补登 store）。
        """
        existing_id = self._by_agent.get(agent_name)
        if existing_id is not None and existing_id in self._by_id:
            return self._by_id[existing_id]

        if self.sandbox is None:
            raise SnapshotError("SandboxExecutor is required for workspace operations")

        ws_path = os.path.join(self._root_path, agent_name)
        record = WorkspaceRecord(
            name=agent_name,
            provider_type="git",
            subject_id=self._subject_id,
            locator=path_to_locator(ws_path),
        )
        provider = GitWorkspaceProvider(self.sandbox)
        try:
            await provider.init(record)
        except WorkspaceProviderError as exc:
            raise SnapshotError(str(exc)) from exc

        workspace = AgentWorkspace(
            name=agent_name,
            path=ws_path,
            sandbox=self.sandbox,
            record=record,
            provider=provider,
        )
        self._by_id[record.workspace_id] = workspace
        self._by_agent[agent_name] = record.workspace_id

        # store 就绪则补登；未就绪降级（marker 已落盘，待 start adopt）
        if self._started and self._store is not None:
            await self._persist(record)

        logger.info("Created workspace for agent '%s' at %s", agent_name, ws_path)
        return workspace

    async def destroy_workspace(self, agent_name: str) -> None:
        workspace_id = self._by_agent.get(agent_name)
        workspace = self._by_id.pop(workspace_id, None) if workspace_id else None
        self._by_agent.pop(agent_name, None)
        if workspace is None:
            return
        await workspace.provider.destroy(workspace.record)
        if self._store is not None and workspace_id is not None:
            try:
                await self._store.soft_delete(workspace_id)
            except Exception:  # noqa: BLE001
                logger.warning("Soft-delete failed for %s", workspace_id, exc_info=True)
        logger.info("Destroyed workspace for agent '%s' at %s", agent_name, workspace.path)

    def get_workspace(self, agent_name: str) -> AgentWorkspace | None:
        workspace_id = self._by_agent.get(agent_name)
        if workspace_id is None:
            return None
        return self._by_id.get(workspace_id)

    def list_workspaces(self) -> list[str]:
        return list(self._by_agent.keys())

    # ─── workspace_id 一等接口（W5/W6 对接点）───

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

        provider_type 给定则用该 provider；否则由 registry.detect 探测。经 provider
        init（目录不存在则创建）或 adopt（有 marker 则认领）登记 store + 内存。
        """
        if self._registry is None:
            raise SnapshotError(
                "WorkspaceManager not started: registry unavailable for register_workspace"
            )
        pt = provider_type
        provider = self._registry.get(pt) if pt is not None else self._registry.detect(locator)
        if provider is None:
            raise SnapshotError(f"Cannot detect provider for locator: {locator}")
        # 先尝试 adopt（认领已有 marker 目录），失败则 init（新建/重写）
        try:
            adopt_result = await provider.adopt(locator)
        except Exception as exc:  # noqa: BLE001
            raise SnapshotError(f"adopt failed: {exc}") from exc
        if adopt_result is not None and adopt_result.subject_id == self._subject_id:
            ws_path = locator_to_path(locator)
            record = WorkspaceRecord(
                workspace_id=adopt_result.workspace_id,
                name=name or adopt_result.name or os.path.basename(ws_path),
                provider_type=adopt_result.provider_type,
                subject_id=adopt_result.subject_id,
                locator=locator,
            )
        else:
            ws_path = locator_to_path(locator)
            record = WorkspaceRecord(
                name=name or os.path.basename(ws_path),
                provider_type=provider.provider_type,
                subject_id=self._subject_id,
                locator=locator,
            )
            try:
                if self.sandbox is not None:
                    self.sandbox.allow_external_workspace(ws_path)
                await provider.init(record)
            except WorkspaceProviderError as exc:
                if self.sandbox is not None:
                    self.sandbox.disallow_external_workspace(ws_path)
                raise SnapshotError(str(exc)) from exc
        # 去重：同 workspace_id 已登记则返回现有
        existing = self._by_id.get(record.workspace_id)
        if existing is not None:
            return existing
        self._index_record(record)
        if self._store is not None:
            await self._persist(record)
        logger.info("Registered workspace %s (%s)", record.workspace_id, locator)
        return self._by_id[record.workspace_id]

    async def unregister_workspace(self, workspace_id: str) -> None:
        """移除注册关系但保留物理目录，供 Project 创建失败安全补偿。"""
        workspace = self._by_id.pop(workspace_id, None)
        if workspace is None:
            return
        if self.sandbox is not None:
            self.sandbox.disallow_external_workspace(workspace.path)
        stale_names = [name for name, wid in self._by_agent.items() if wid == workspace_id]
        for name in stale_names:
            self._by_agent.pop(name, None)
        if self._store is not None:
            await self._store.soft_delete(workspace_id)
        try:
            os.unlink(os.path.join(workspace.path, MARKER_FILENAME))
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Failed to remove workspace marker for %s", workspace_id)
        logger.info("Unregistered workspace %s (%s)", workspace_id, workspace.record.locator)
