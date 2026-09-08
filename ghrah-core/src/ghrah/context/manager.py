# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ContextManager：上下文管理器门面类。

整合 SessionRuntime + StateManager + MessageStore，
为 ActorAgent 提供统一的上下文管理接口。

核心职责：
- 迭代生命周期：begin_iteration → commit_iteration / rollback_iteration
- 消息+状态协调：commit 时自动计算 delta、定期存储 snapshot、管理 state 事务
- 上下文构建：build_execution_context 供 Ability/Hook 使用
- 子 Agent 继承：fork_for_sub_agent 创建独立但继承的上下文
- Session 管理：create_session / activate_session / list_sessions
- Branch 管理：create_branch / activate_branch / list_branches
- 持久化：persist/restore 异步保存和恢复完整链式状态
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ghrah.context.action_session import ActionSession
from ghrah.context.branch import ActionBranch
from ghrah.context.chain import ActionChain
from ghrah.context.message_store import MessageStore
from ghrah.context.node import ContextNode
from ghrah.context.persistence import ContextChanges, PersistenceBackend
from ghrah.context.session_runtime import SessionRuntime
from ghrah.context.state import StateManager
from ghrah.context.window import WindowManager
from ghrah.core.window_protocol import MessageFactory

if TYPE_CHECKING:
    from ghrah.abilities.context import AbilityExecutionContext
    from ghrah.core.message import AgentMessage
    from ghrah.types.config_types import AgentConfig

logger = logging.getLogger(__name__)

__all__ = ["ContextManager"]


class ContextManager:
    """上下文管理器门面类 — 管理多个单 Root Session。

    为 ActorAgent 的驱动循环提供统一的上下文管理，支持：
    - 原子性迭代（事务性状态变更 + 消息管理）
    - 链式历史（类似 Git 的不可变节点链）
    - Session 管理（独立 Root + 元数据）
    - Branch 管理（稳定 Head 引用）
    - 回滚即分支（rollback 自动创建新 Branch）
    - 子 Agent 继承（fork_for_sub_agent 创建独立上下文）
    - 异步持久化（persist/restore）

    迭代生命周期：
        begin_iteration() → add_messages() / apply_state_changes()
        → commit_iteration() 或 rollback_iteration()

    Args:
        agent_name: 所属 Agent 名称
        initial_state: 初始 Agent 状态
        snapshot_interval: 消息快照间隔，默认 5
        system_prompt: 系统提示词
        window_manager: 窗口管理器（可选）
        persistence: 持久化后端（可选，None 则不持久化）
        auto_persist: 是否在每次 commit/rollback 后自动持久化节点，默认 False
        initial_messages: Root 初始消息（system_prompt 会显式插入最前）
        origin_session_id: Root 来源 Session ID，必须与 origin_node_id 同时提供
        origin_node_id: Root 来源节点 ID，只记录 provenance，不建立跨 Session 父边
        session_metadata: 初始 Session 元数据
        root_metadata: 初始 Root 节点元数据
    """

    def __init__(
        self,
        agent_name: str,
        initial_state: dict[str, Any] | None = None,
        snapshot_interval: int = 5,
        system_prompt: str = "",
        window_manager: WindowManager | None = None,
        persistence: PersistenceBackend | None = None,
        auto_persist: bool = False,
        message_factory: MessageFactory | None = None,
        initial_messages: list[Any] | None = None,
        origin_session_id: str | None = None,
        origin_node_id: str | None = None,
        session_metadata: dict[str, Any] | None = None,
        root_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._agent_name = agent_name
        self._state_manager = StateManager(initial_state)
        self._message_store = MessageStore(snapshot_interval=snapshot_interval)
        self._system_prompt = system_prompt
        self._window_manager = window_manager
        self._persistence = persistence
        self._auto_persist = auto_persist
        self._message_factory = message_factory
        self._pending_messages: list[Any] = []
        self._in_iteration: bool = False
        self._pending_compaction: list[dict[str, Any]] = []
        self._persist_tasks: set[asyncio.Task[Any]] = set()
        self._persist_lock = asyncio.Lock()

        # 初始化默认 Session：一次性创建 Root 与 main Branch。
        effective_messages = list(initial_messages or [])
        if system_prompt:
            if message_factory is None:
                raise ValueError(
                    "message_factory is required when system_prompt is provided. "
                    "Pass a MessageFactory instance (e.g. ChatMessageFactory())."
                )
            msg = message_factory.create_message(role="system", text=system_prompt)
            effective_messages.insert(0, msg)
        self._message_store.extend(effective_messages)

        root_runtime = SessionRuntime.create(
            agent_name=agent_name,
            system_prompt=system_prompt,
            agent_state=initial_state or {},
            messages=effective_messages,
            origin_session_id=origin_session_id,
            origin_node_id=origin_node_id,
            metadata=session_metadata,
            root_metadata=root_metadata,
        )
        self._session_runtimes: dict[str, SessionRuntime] = {
            root_runtime.session.session_id: root_runtime
        }
        self._active_session_id = root_runtime.session.session_id

        # 建立初始快照基准
        self._message_store.take_snapshot(0)
        if (
            self._auto_persist
            and self._persistence is not None
            and getattr(self._persistence, "connected", True)
        ):
            self._schedule_changes(
                ContextChanges(
                    agent_name=self._agent_name,
                    sessions=(root_runtime.session,),
                    branches=tuple(root_runtime.branches.values()),
                    nodes=(root_runtime.active_head,),
                    active_session_id=self._active_session_id,
                ),
                label=f"initialize session {root_runtime.session.session_id}",
            )

    # ----------------------------------------------------------------
    # 属性
    # ----------------------------------------------------------------

    @property
    def agent_name(self) -> str:
        """所属 Agent 名称。"""
        return self._agent_name

    @property
    def chain(self) -> ActionChain:
        """当前激活 Session 的单 Root ActionChain。"""
        return self._active_runtime.chain

    @property
    def active_head(self) -> ContextNode:
        """由 active_session_id 与 active_branch_id 推导的唯一运行 Head。"""
        return self._active_runtime.active_head

    @property
    def message_store(self) -> MessageStore:
        """底层消息存储（只读访问）。"""
        return self._message_store

    @property
    def in_iteration(self) -> bool:
        """是否在迭代中。"""
        return self._in_iteration

    @property
    def window_manager(self) -> WindowManager | None:
        """窗口管理器（只读访问）。"""
        return self._window_manager

    @property
    def persistence(self) -> PersistenceBackend | None:
        """持久化后端（只读访问）。"""
        return self._persistence

    @property
    def auto_persist(self) -> bool:
        """是否自动持久化。"""
        return self._auto_persist

    @property
    def message_factory(self) -> MessageFactory | None:
        """消息工厂（只读访问）。"""
        return self._message_factory

    @property
    def message_count(self) -> int:
        """当前 MessageStore 中的消息数量。"""
        return self._message_store.count

    @property
    def active_session_id(self) -> str:
        """当前激活 Session 的稳定 ID。"""
        return self._active_session_id

    @property
    def _active_runtime(self) -> SessionRuntime:
        """当前激活 Session 运行时。"""
        return self._session_runtimes[self._active_session_id]

    # ----------------------------------------------------------------
    # Session 管理
    # ----------------------------------------------------------------

    def create_session(
        self,
        *,
        origin_session_id: str | None = None,
        origin_node_id: str | None = None,
        system_prompt: str | None = None,
        initial_state: dict[str, Any] | None = None,
        initial_messages: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActionSession:
        """创建拥有独立 Root 的 Session，不隐式激活。

        传入 origin_session_id + origin_node_id 时，新 Root 复制来源节点的
        state/messages，但 parent_id 仍为 None。
        """
        self._ensure_not_in_iteration("create a session")
        if (origin_session_id is None) != (origin_node_id is None):
            raise ValueError(
                "origin_session_id and origin_node_id must either both be set or both be None"
            )
        if origin_session_id is not None and (
            initial_state is not None or initial_messages is not None
        ):
            raise ValueError("origin context and explicit initial context are mutually exclusive")

        effective_prompt = self._system_prompt if system_prompt is None else system_prompt
        effective_state = initial_state or {}
        effective_messages = list(initial_messages or [])
        if origin_session_id is not None and origin_node_id is not None:
            source = self._get_runtime(origin_session_id)
            source_node = source.chain.checkout(origin_node_id)
            if source_node is None:
                raise ValueError(
                    f"Node '{origin_node_id}' not found in session '{origin_session_id}'."
                )
            effective_state = source_node.agent_state
            effective_messages = self._messages_from_history(
                source.chain.get_history_from(origin_node_id)
            )
            effective_messages = [
                message
                for message in effective_messages
                if getattr(message, "role", None) != "system"
            ]

        if effective_prompt:
            if self._message_factory is None:
                raise ValueError("message_factory is required when system_prompt is provided")
            system_message = self._message_factory.create_message(
                role="system", text=effective_prompt
            )
            effective_messages.insert(0, system_message)

        runtime = SessionRuntime.create(
            agent_name=self._agent_name,
            system_prompt=effective_prompt,
            agent_state=effective_state,
            messages=effective_messages,
            origin_session_id=origin_session_id,
            origin_node_id=origin_node_id,
            metadata=metadata,
        )
        self._session_runtimes[runtime.session.session_id] = runtime
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(
                    agent_name=self._agent_name,
                    sessions=(runtime.session,),
                    branches=tuple(runtime.branches.values()),
                    nodes=(runtime.active_head,),
                    active_session_id=self._active_session_id,
                ),
                label=f"create session {runtime.session.session_id}",
            )
        return runtime.session

    def list_sessions(self, *, include_deleted: bool = False) -> list[ActionSession]:
        """列出独立 Root Session；默认隐藏删除墓碑。"""
        sessions = [runtime.session for runtime in self._session_runtimes.values()]
        if include_deleted:
            return sessions
        return [session for session in sessions if not session.metadata.get("deleted")]

    def get_active_session(self) -> ActionSession:
        """获取当前激活 Session。"""
        return self._active_runtime.session

    def activate_session(self, session_id: str) -> None:
        """显式激活 Session 并完整恢复其记忆的 Branch Head 上下文。"""
        self._ensure_not_in_iteration("activate a session")
        runtime = self._get_runtime(session_id)
        if runtime.session.metadata.get("deleted"):
            raise ValueError("Cannot activate a deleted session.")
        self._active_session_id = session_id
        self._restore_active_context()
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(
                    agent_name=self._agent_name,
                    active_session_id=self._active_session_id,
                ),
                label=f"activate session {session_id}",
            )

    def get_session(self, session_id: str) -> ActionSession:
        """获取指定 ID 的 session。

        Args:
            session_id: session ID

        Returns:
            对应的 Session 实例

        Raises:
            KeyError: session 不存在
        """
        if session_id not in self._session_runtimes:
            raise KeyError(f"Session '{session_id}' not found.")
        return self._session_runtimes[session_id].session

    def create_branch(
        self,
        *,
        session_id: str,
        name: str,
        from_node_id: str | None = None,
        parent_branch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActionBranch:
        """在同一 Session 内从指定节点创建 Branch，不隐式激活。"""
        self._ensure_not_in_iteration("create a branch")
        runtime = self._get_runtime(session_id)
        if runtime.session.metadata.get("deleted"):
            raise ValueError("Cannot create a branch in a deleted session.")
        branch = runtime.create_branch(
            name=name,
            parent_branch_id=parent_branch_id,
            fork_point_node_id=from_node_id,
            metadata=metadata,
        )
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(
                    agent_name=self._agent_name,
                    branches=(branch,),
                ),
                label=f"create branch {branch.branch_id}",
            )
        return branch

    def list_branches(
        self, session_id: str, *, include_deleted: bool = False
    ) -> list[ActionBranch]:
        """列出 Session 内的 Branch；默认隐藏删除墓碑。"""
        branches = list(self._get_runtime(session_id).branches.values())
        if include_deleted:
            return branches
        return [branch for branch in branches if not branch.metadata.get("deleted")]

    def activate_branch(self, session_id: str, branch_id: str) -> None:
        """显式激活当前 Session 内的 Branch 并完整恢复上下文。"""
        self._ensure_not_in_iteration("activate a branch")
        if session_id != self._active_session_id:
            raise ValueError("activate the session before activating one of its branches")
        runtime = self._get_runtime(session_id)
        if runtime.get_branch(branch_id).metadata.get("deleted"):
            raise ValueError("Cannot activate a deleted branch.")
        runtime.activate_branch(branch_id)
        self._restore_active_context()
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(
                    agent_name=self._agent_name,
                    sessions=(runtime.session,),
                    active_session_id=self._active_session_id,
                ),
                label=f"activate branch {branch_id}",
            )

    def get_branch_head(self, session_id: str, branch_id: str) -> ContextNode:
        """获取指定 Session/Branch 的 Head。"""
        runtime = self._get_runtime(session_id)
        branch = runtime.get_branch(branch_id)
        node = runtime.chain.checkout(branch.head_node_id)
        if node is None:  # pragma: no cover - SessionRuntime 已校验
            raise RuntimeError("branch head is missing")
        return node

    def archive_session(self, session_id: str) -> ActionSession:
        """归档指定 session（标记 metadata.archived=True）。

        Args:
            session_id: 要归档的 session ID

        Returns:
            归档后的 Session 实例（新对象，dataclasses.replace 创建）

        Raises:
            KeyError: session 不存在
        """
        self._ensure_not_in_iteration("archive a session")
        runtime = self._get_runtime(session_id, error_type=KeyError)
        if session_id == self._active_session_id:
            raise ValueError("Cannot archive the active session.")
        session = runtime.session
        archived = dataclasses.replace(
            session,
            metadata={**session.metadata, "archived": True},
        )
        runtime.session = archived
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(agent_name=self._agent_name, sessions=(archived,)),
                label=f"archive session {session_id}",
            )
        return archived

    def delete_session(self, session_id: str) -> ActionSession:
        """删除指定 session。

        不能删除当前活跃的 session。

        Args:
            session_id: 要删除的 session ID

        Returns:
            被删除的 Session 实例

        Raises:
            KeyError: session 不存在
            ValueError: 试图删除当前活跃 session
        """
        if session_id not in self._session_runtimes:
            raise KeyError(f"Session '{session_id}' not found.")
        if session_id == self._active_session_id:
            raise ValueError("Cannot delete the active session.")
        self._ensure_not_in_iteration("delete a session")
        runtime = self._session_runtimes[session_id]
        deleted = dataclasses.replace(
            runtime.session,
            metadata={**runtime.session.metadata, "deleted": True},
        )
        runtime.session = deleted
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(
                    agent_name=self._agent_name,
                    sessions=(deleted,),
                ),
                label=f"delete session {session_id}",
            )
        return deleted

    def archive_branch(self, session_id: str, branch_id: str) -> ActionBranch:
        """归档非运行 Branch，同时保留不可变节点的来源引用。"""
        self._ensure_not_in_iteration("archive a branch")
        runtime = self._get_runtime(session_id)
        if session_id == self._active_session_id and branch_id == runtime.session.active_branch_id:
            raise ValueError("Cannot archive the active branch.")
        branch = runtime.get_branch(branch_id)
        archived = dataclasses.replace(
            branch,
            metadata={**branch.metadata, "archived": True},
        )
        runtime.branches[branch_id] = archived
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(agent_name=self._agent_name, branches=(archived,)),
                label=f"archive branch {branch_id}",
            )
        return archived

    def delete_branch(self, session_id: str, branch_id: str) -> ActionBranch:
        """删除非运行 Branch（墓碑），不破坏节点 provenance 与拓扑。"""
        self._ensure_not_in_iteration("delete a branch")
        runtime = self._get_runtime(session_id)
        if session_id == self._active_session_id and branch_id == runtime.session.active_branch_id:
            raise ValueError("Cannot delete the active branch.")
        branch = runtime.get_branch(branch_id)
        deleted = dataclasses.replace(
            branch,
            metadata={**branch.metadata, "deleted": True},
        )
        runtime.branches[branch_id] = deleted
        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(agent_name=self._agent_name, branches=(deleted,)),
                label=f"delete branch {branch_id}",
            )
        return deleted

    def _get_runtime(
        self, session_id: str, *, error_type: type[Exception] = ValueError
    ) -> SessionRuntime:
        """获取 SessionRuntime，并统一产生领域错误。"""
        try:
            return self._session_runtimes[session_id]
        except KeyError as exc:
            raise error_type(f"Session '{session_id}' not found.") from exc

    def _ensure_not_in_iteration(self, operation: str) -> None:
        """禁止在迭代事务中改变运行 Head。"""
        if self._in_iteration:
            raise RuntimeError(f"Cannot {operation} during an iteration")

    @staticmethod
    def _messages_from_history(history: list[ContextNode]) -> list[Any]:
        """从最近快照与后续 delta 重建 Head 消息。"""
        snapshot_index = next(
            (
                index
                for index in range(len(history) - 1, -1, -1)
                if history[index].is_snapshot and history[index].messages_snapshot is not None
            ),
            None,
        )
        if snapshot_index is None:
            return [message for node in history for message in node.messages_delta]
        messages = list(history[snapshot_index].messages_snapshot or [])
        for node in history[snapshot_index + 1 :]:
            messages.extend(node.messages_delta)
        return messages

    def _restore_active_context(self) -> None:
        """从当前 Session/Branch Head 恢复 state 与 MessageStore。"""
        runtime = self._active_runtime
        head = runtime.active_head
        messages = self._messages_from_history(runtime.get_history())
        self._state_manager.reset(head.agent_state)
        self._message_store = MessageStore(snapshot_interval=self._message_store.snapshot_interval)
        self._message_store.extend(messages)
        self._message_store.take_snapshot(head.iteration)
        self._system_prompt = runtime.session.system_prompt
        self._pending_messages = []

    # ----------------------------------------------------------------
    # 迭代生命周期
    # ----------------------------------------------------------------

    def begin_iteration(self) -> None:
        """开始新迭代。

        开启状态事务，清空 pending_messages 缓冲区。

        Raises:
            RuntimeError: 已有迭代在进行中
        """
        if self._in_iteration:
            raise RuntimeError("Iteration already in progress")
        self._state_manager.begin_transaction()
        self._pending_messages = []
        self._in_iteration = True

    def apply_state_changes(self, changes: dict[str, Any]) -> dict[str, Any]:
        """在当前迭代的事务中应用状态变更。

        变更累积到 pending 区，commit 时才生效。

        Args:
            changes: 要应用的变更（支持嵌套 dict 递归合并）

        Returns:
            合并后的预期状态（深拷贝）

        Raises:
            RuntimeError: 没有活跃的迭代
        """
        if not self._in_iteration:
            raise RuntimeError("No iteration in progress")
        return self._state_manager.apply_changes(changes)

    def add_messages(self, messages: list[Any]) -> None:
        """收集本轮新消息到缓冲区。

        消息在 commit_iteration 时才写入 MessageStore，
        rollback_iteration 时会被丢弃。

        Args:
            messages: ChatMessage 列表
        """
        if self._in_iteration:
            self._pending_messages.extend(messages)
        else:
            self._message_store.extend(messages)

    def commit_iteration(
        self,
        ability_names: list[str] | None = None,
        action_results: list[dict[str, Any]] | None = None,
        state_changes: dict[str, Any] | None = None,
        llm_metadata: dict[str, Any] | None = None,
    ) -> ContextNode:
        """提交当前迭代。

        流程：
        1. 如果有额外的 state_changes，先应用
        2. 提交状态事务
        3. 将 pending_messages 写入 MessageStore
        4. 计算 delta / 判断是否需要 snapshot
        5. 创建链式节点

        Args:
            ability_names: 本轮执行的 ability 名称列表
            action_results: 本轮执行结果列表
            state_changes: 额外的状态变更（可选）
            llm_metadata: LLM 响应元数据

        Returns:
            新创建的 ContextNode

        Raises:
            RuntimeError: 没有活跃的迭代
        """
        if not self._in_iteration:
            raise RuntimeError("No iteration in progress")

        effective_names: list[str]
        effective_result: Any | None

        if ability_names is not None:
            effective_names = ability_names
            effective_result = action_results
        else:
            effective_names = ["unknown"]
            effective_result = None

        # 1. 如果有额外的 state_changes，先应用
        if state_changes:
            self._state_manager.apply_changes(state_changes)

        # 2. 提交状态事务
        new_state = self._state_manager.commit()

        # 3. 将 pending_messages 写入 MessageStore
        self._message_store.extend(self._pending_messages)

        # 4. 计算迭代号（基于当前 Branch Head）
        iteration = self._active_runtime.active_head.iteration + 1

        # 5. delta 为当前轮次新增的消息
        delta = list(self._pending_messages)

        # 6. 判断是否需要快照
        is_snapshot = self._message_store.should_snapshot(iteration)
        if is_snapshot:
            snapshot = self._message_store.take_snapshot(iteration)
        else:
            snapshot = None

        # 7. 合并 llm_metadata 到节点 metadata
        node_metadata: dict[str, Any] = {}
        if llm_metadata:
            node_metadata.update(llm_metadata)

        # 7.1 合并窗口压缩事件记录（内部权威，来源为 get_llm_messages 的 stash）
        if self._pending_compaction:
            node_metadata["compaction"] = list(self._pending_compaction)
            self._pending_compaction = []

        # 8. 创建链式节点并前移当前 Branch Head
        node = self._active_runtime.commit_node(
            ability_names=effective_names,
            agent_state=new_state,
            messages_delta=delta,
            messages_snapshot=snapshot,
            is_snapshot=is_snapshot,
            action_results=effective_result or [],
            metadata=node_metadata or None,
        )

        # 10. 清理迭代状态
        self._pending_messages = []
        self._in_iteration = False

        # 11. 自动持久化（如果启用）
        if self._auto_persist and self._persistence is not None:
            self._schedule_persist_node(node)

        return node

    # ----------------------------------------------------------------
    # 回滚即分支
    # ----------------------------------------------------------------

    def rollback_iteration(self, error: Exception) -> ActionBranch:
        """回滚未提交迭代，从当前 Head 创建并激活重试 Branch。

        未提交迭代不会产生 ContextNode，因此重试 Branch 的 fork point 就是
        迭代开始时的 Head。错误信息存在 Branch metadata 中。

        Args:
            error: 导致回滚的异常

        Returns:
            新创建并已激活的重试 Branch

        Raises:
            RuntimeError: 没有活跃的迭代
        """
        if not self._in_iteration:
            raise RuntimeError("No iteration in progress")

        # 1. 回滚状态事务
        self._state_manager.rollback()

        runtime = self._active_runtime
        current_branch = runtime.active_branch
        current_head = runtime.active_head
        retry_number = len(runtime.branches)
        branch = runtime.create_branch(
            name=f"retry-{retry_number}",
            parent_branch_id=current_branch.branch_id,
            fork_point_node_id=current_head.id,
            metadata={
                "is_rollback": True,
                "rollback_from_branch_id": current_branch.branch_id,
                "rollback_from_node_id": current_head.id,
                "rollback_to_node_id": current_head.id,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
        runtime.activate_branch(branch.branch_id)

        # 8. 清理迭代状态
        self._pending_messages = []
        self._pending_compaction = []
        self._in_iteration = False

        if self._auto_persist and self._persistence is not None:
            self._schedule_changes(
                ContextChanges(
                    agent_name=self._agent_name,
                    sessions=(runtime.session,),
                    branches=(branch,),
                    active_session_id=self._active_session_id,
                ),
                label=f"rollback to branch {branch.branch_id}",
            )
        return branch

    # ----------------------------------------------------------------
    # 上下文构建
    # ----------------------------------------------------------------

    def build_execution_context(
        self,
        message: AgentMessage | None = None,
        config: AgentConfig | None = None,
        system_prompt: str | None = None,
        context_filter: Callable | None = None,
    ) -> AbilityExecutionContext:
        """构建 AbilityExecutionContext。

        Args:
            message: 输入消息（可选，保留向后兼容）
            config: Agent 配置（可选）
            system_prompt: 覆盖默认 system_prompt（可选）
            context_filter: 上下文过滤函数（可选）

        Returns:
            初始化后的 AbilityExecutionContext
        """
        from ghrah.abilities.context import AbilityExecutionContext

        return AbilityExecutionContext(
            current_ability_name="",
            agent_state=self._state_manager.current,
            context_manager=self,
        )

    async def get_llm_messages(
        self,
        max_tokens: int | None = None,
        filter_fn: Callable | None = None,
    ) -> list[Any]:
        """获取 LLM 消息列表。

        返回经过窗口管理策略处理后的消息列表。
        如果配置了 WindowManager，会自动应用压缩策略确保消息在 token 预算内。

        Args:
            max_tokens: 最大 token 数（可选，覆盖 WindowManager 的默认值）
            filter_fn: 消息过滤函数（可选）

        Returns:
            ChatMessage 列表
        """
        messages = self._message_store.current_messages

        # 合并 pending_messages（迭代中尚未 commit 的消息）
        if self._in_iteration and self._pending_messages:
            messages = messages + list(self._pending_messages)
            logger.debug(
                "get_llm_messages: merged %d pending messages into LLM context (total=%d)",
                len(self._pending_messages),
                len(messages),
            )

        if filter_fn is not None:
            messages = [m for m in messages if filter_fn(m)]

        # 应用窗口管理策略
        if self._window_manager is not None:
            budget = max_tokens or self._window_manager.max_tokens
            messages = await self._window_manager.apply(messages, max_tokens=budget)
            records = self._window_manager.drain_compaction_records()
            if records:
                self._pending_compaction.extend(records)

        return messages

    def get_cumulative_token_usage(self) -> dict[str, int]:
        """从链历史中累计计算总 token 用量。

        遍历所有链节点的 metadata.token_usage 字段，累加得到总和。

        Returns:
            包含 input_tokens、output_tokens、total_tokens 的 dict
        """
        total: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        for node in self._active_runtime.get_history():
            usage = node.metadata.get("token_usage", {})
            if isinstance(usage, dict):
                total["input_tokens"] += usage.get("input_tokens", 0)
                total["output_tokens"] += usage.get("output_tokens", 0)
                total["total_tokens"] += usage.get("total_tokens", 0)
        return total

    # ----------------------------------------------------------------
    # 子 Agent 支持
    # ----------------------------------------------------------------

    def fork_for_sub_agent(
        self,
        agent_name: str,
        system_prompt: str | None = None,
        state_filter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        snapshot_interval: int | None = None,
    ) -> ContextManager:
        """为子 Agent fork 出独立的上下文。

        向后兼容的子 Agent fork 方法。内部调用 create_rebased_context()。

        注意：如果 system_prompt=None，旧行为是继承父 Agent 的 system_prompt。
        这与 rebase 的默认语义（不继承 system_prompt）不同。
        为保持向后兼容，当 system_prompt=None 时使用父 Agent 的 system_prompt。

        Args:
            agent_name: 子 Agent 名称
            system_prompt: 覆盖 system_prompt（可选，None 继承父 Agent 的）
            state_filter: 状态过滤函数，选择性继承状态（可选）
            snapshot_interval: 快照间隔（可选，默认使用父 CM 的设置）

        Returns:
            子 Agent 的 ContextManager
        """
        from ghrah.context.rebase import create_rebased_context

        effective_prompt = system_prompt or self._system_prompt
        return create_rebased_context(
            source_cm=self,
            agent_name=agent_name,
            system_prompt=effective_prompt,
            inherit_messages=True,
            inherit_state=True,
            state_filter=state_filter,
            snapshot_interval=snapshot_interval,
        )

    # ----------------------------------------------------------------
    # 查询
    # ----------------------------------------------------------------

    def get_history(
        self,
        limit: int = -1,
        *,
        session_id: str | None = None,
        branch_id: str | None = None,
    ) -> list[ContextNode]:
        """获取链历史。

        Args:
            limit: 限制返回数量。-1 表示全部，>0 返回最近 N 个。

        Returns:
            历史节点列表（根在前）
        """
        runtime = self._get_runtime(session_id or self._active_session_id)
        return runtime.get_history(branch_id=branch_id, limit=limit)

    def get_messages(
        self,
        *,
        session_id: str | None = None,
        branch_id: str | None = None,
    ) -> list[Any]:
        """从指定 Session/Branch Head 重建完整消息上下文。"""
        history = self.get_history(session_id=session_id, branch_id=branch_id)
        return self._messages_from_history(history)

    def get_current_state(self) -> dict[str, Any]:
        """获取当前状态的深拷贝。

        Returns:
            当前状态快照
        """
        return self._state_manager.get_snapshot()

    def set_state(self, key: str, value: Any) -> None:
        """设置单个状态键值（迭代外 API）。

        直接操作 StateManager，不经过事务。仅限迭代外调用；
        迭代中应使用 apply_state_changes() 写入事务 pending 区。

        Args:
            key: 状态键
            value: 状态值

        Raises:
            RuntimeError: 在迭代中调用（应改用 apply_state_changes()）
        """
        if self._in_iteration:
            raise RuntimeError(
                "Cannot call set_state() during iteration. Use apply_state_changes() instead."
            )
        current = self._state_manager.current
        current[key] = value
        self._state_manager.reset(new_state=current)

    def update_state(self, partial: dict[str, Any]) -> None:
        """合并更新多个状态键（迭代外 API）。

        直接操作 StateManager，不经过事务。仅限迭代外调用；
        迭代中应使用 apply_state_changes() 写入事务 pending 区。

        Args:
            partial: 要合并的状态变更

        Raises:
            RuntimeError: 在迭代中调用（应改用 apply_state_changes()）
        """
        if self._in_iteration:
            raise RuntimeError(
                "Cannot call update_state() during iteration. Use apply_state_changes() instead."
            )
        current = self._state_manager.current
        current.update(partial)
        self._state_manager.reset(new_state=current)

    def get_branch_heads(self, session_id: str | None = None) -> dict[str, ContextNode]:
        """获取指定 Session 所有 Branch 的 Head。

        Returns:
            branch_id → Head ContextNode 的映射
        """
        runtime = self._get_runtime(session_id or self._active_session_id)
        result: dict[str, ContextNode] = {}
        for branch_id, branch in runtime.branches.items():
            node = runtime.chain.checkout(branch.head_node_id)
            if node is not None:
                result[branch_id] = node
        return result

    def get_chain_node(self, node_id: str, session_id: str | None = None) -> ContextNode | None:
        """获取指定 ID 的链节点。

        Args:
            node_id: 节点 ID

        Returns:
            对应的 ContextNode，不存在则返回 None
        """
        runtime = self._get_runtime(session_id or self._active_session_id)
        return runtime.chain.checkout(node_id)

    # ----------------------------------------------------------------
    # 持久化
    # ----------------------------------------------------------------

    async def persist(self) -> None:
        """显式持久化当前完整状态到后端。

        保存内容：
        1. 链的所有节点（遍历 ActionChain 内部节点）
        2. 链元信息（分支映射 + 当前状态 + 活跃 session）
        3. 当前完整消息列表
        4. 所有 session

        Raises:
            RuntimeError: 未配置持久化后端
        """
        if self._persistence is None:
            logger.warning("persist() called but no persistence backend configured")
            return

        # 等待所有后台 auto-persist 任务完成，避免竞态
        await self.wait_for_persist()
        await self._persist_complete_checkpoint()

    async def _persist_complete_checkpoint(self) -> None:
        """写完整 checkpoint；调用方负责避免把当前 task 纳入 wait。"""
        if self._persistence is None:
            return

        async with self._persist_lock:
            runtimes = list(self._session_runtimes.values())
            changes = ContextChanges(
                agent_name=self._agent_name,
                active_session_id=self._active_session_id,
                sessions=tuple(runtime.session for runtime in runtimes),
                branches=tuple(
                    branch for runtime in runtimes for branch in runtime.branches.values()
                ),
                nodes=tuple(node for runtime in runtimes for node in runtime.chain.nodes),
            )
            await self._persistence.apply_changes(changes)
            logger.debug(
                "Upserted context for agent '%s': %d sessions, %d branches, %d nodes",
                self._agent_name,
                len(changes.sessions),
                len(changes.branches),
                len(changes.nodes),
            )

    async def restore(self, agent_name: str) -> None:
        """从完整 checkpoint 恢复多 SessionRuntime 和当前运行上下文。

        Args:
            agent_name: 要恢复的 Agent 名称

        Raises:
            RuntimeError: 未配置持久化后端
            ValueError: 后端中无该 agent 的数据
        """
        if self._persistence is None:
            raise RuntimeError("No persistence backend configured")

        checkpoint = await self._persistence.load_checkpoint(agent_name)
        if checkpoint is None:
            raise ValueError(f"No persisted data found for agent '{agent_name}'")

        branches_by_session: dict[str, list[ActionBranch]] = {}
        nodes_by_session: dict[str, list[ContextNode]] = {}
        for branch in checkpoint.branches:
            branches_by_session.setdefault(branch.session_id, []).append(branch)
        for node in checkpoint.nodes:
            nodes_by_session.setdefault(node.session_id, []).append(node)

        runtimes = {
            session.session_id: SessionRuntime.restore(
                session=session,
                branches=branches_by_session.get(session.session_id, []),
                nodes=nodes_by_session.get(session.session_id, []),
            )
            for session in checkpoint.sessions
        }
        self._agent_name = agent_name
        self._session_runtimes = runtimes
        self._active_session_id = checkpoint.active_session_id
        self._restore_active_context()
        self._in_iteration = False

        logger.debug(
            "Restored context for agent '%s': %d nodes, %d sessions, %d messages",
            agent_name,
            sum(runtime.chain.node_count for runtime in runtimes.values()),
            len(runtimes),
            self._message_store.count,
        )

    async def wait_for_persist(self) -> None:
        """等待所有待处理的后台持久化任务完成。

        在调用 persist() 前自动调用，也可手动调用以确保所有
        auto-persist 调度的节点保存操作已完成。
        """
        if self._persist_tasks:
            await asyncio.gather(*self._persist_tasks, return_exceptions=True)
            self._persist_tasks.clear()

    def persist_node(self, node: ContextNode) -> None:
        """公共方法：后台异步保存单个节点（不阻塞主循环）。

        包装内部 _schedule_persist_node，供 rebase 等外部场景使用，
        消除对私有方法的直接访问。

        Args:
            node: 要保存的 ContextNode
        """
        self._schedule_persist_node(node)

    # ----------------------------------------------------------------
    # LLM 注入支持
    # ----------------------------------------------------------------

    def inject_llm_into_summary(self, llm: Any) -> None:
        """将 LLM 注入到 WindowManager 的 LLMSummaryStrategy 中。

        遍历 window_manager.strategies（使用只读 property），
        对尚未设置 LLM 的 LLMSummaryStrategy 注入。

        Args:
            llm: 实现 LLMProtocol 的 LLM 实例
        """
        if self._window_manager is None:
            return
        from ghrah.context.strategies.llm_summary import LLMSummaryStrategy

        for strategy in self._window_manager.strategies:
            if isinstance(strategy, LLMSummaryStrategy) and strategy.llm is None:
                strategy.set_llm(llm)

    def _schedule_persist_node(self, node: ContextNode) -> None:
        """后台异步保存单节点与对应 Branch Head 变更。

        Args:
            node: 要保存的 ContextNode
        """
        runtime = self._get_runtime(node.session_id)
        branch = runtime.get_branch(node.created_on_branch_id)
        self._schedule_changes(
            ContextChanges(
                agent_name=self._agent_name,
                branches=(branch,),
                nodes=(node,),
            ),
            label=f"commit node {node.id}",
        )

    def _schedule_changes(self, changes: ContextChanges, *, label: str) -> None:
        """按调度顺序在后台原子应用增量变更集。"""
        if self._persistence is None:
            return
        tasks = self._persist_tasks
        predecessors = tuple(tasks)
        backend = self._persistence

        async def _tracked_save() -> None:
            try:
                if predecessors:
                    await asyncio.gather(*predecessors, return_exceptions=True)
                async with self._persist_lock:
                    await backend.apply_changes(changes)
            except Exception:
                logger.warning(
                    "Failed to persist %s for agent '%s'",
                    label,
                    changes.agent_name,
                    exc_info=True,
                )
            finally:
                tasks.discard(task)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_tracked_save())
            tasks.add(task)
        except RuntimeError:
            logger.debug("No running event loop, skipping auto-persist for %s", label)

    # ----------------------------------------------------------------
    # 内部辅助
    # ----------------------------------------------------------------

    def _get_conversation_history(self) -> list[Any]:
        """获取对话历史（Message 对象列表）。

        Returns:
            消息历史列表
        """
        return []
