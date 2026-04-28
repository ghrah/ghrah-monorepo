"""SubjectService：Subject 的运行时编排器。

全链路测试核心组件。负责：
- WebSocket 连接管理（连接 Gateway）
- 命令分发（execute_ability, persist_*）
- 事件处理（agent_spawned, action_chain_updated）
- HITL 流程（广播请求、接收审批）
- 子系统编排（WorkspaceManager, AbilityRunner, HITLNotary 等）

消息流设计：
- execute_ability 命令在后台 Task 中执行，避免阻塞消息循环
  （因为 HITL 审批需要等待 Observer 响应）
- spawn_agent/send_message 使用 request_id 关联的 Future 等待响应
- hitl_response 通过 HITLNotary.resolve_promise 触发 AbilityRunner 继续
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

import websockets

from ghrah.abilities import ActionOutcome
from ghrah.gateway.protocol import (
    AbilityDefinitionPayload,
    AgentConfigPayload,
    EventType,
    GatewayMessage,
    HITLRequestPayload,
    SystemType,
    generate_request_id,
)
from ghrah.subject.ability_runner import AbilityRunner, AbilityRunnerConfig
from ghrah.subject.config import SubjectConfig
from ghrah.subject.hitl.notary import HITLNotary, HITLPromise
from ghrah.subject.hitl.policy import HITLPolicy, HITLVerdict
from ghrah.subject.ledger.chain import ActionChainLedger
from ghrah.subject.permission_checker import PermissionChecker
from ghrah.subject.persistence.service import SubjectPersistenceService
from ghrah.subject.sandbox.executor import SandboxExecutor, SandboxExecutorConfig
from ghrah.subject.sandbox.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

__all__ = ["SubjectService"]

_CORE_EVENT_TYPES = frozenset({
    "agent_spawned",
    "agent_terminated",
    "agent_response",
    "action_chain_updated",
    "agent_error",
    "health_status",
})

_PERSIST_COMMANDS = frozenset({
    "persist_save_node",
    "persist_load_node",
    "persist_load_chain",
    "persist_save_chain_meta",
    "persist_load_chain_meta",
    "persist_save_messages",
    "persist_load_messages",
    "persist_delete_chain",
    "persist_list_agents",
})

_WORKSPACE_COMMANDS = frozenset({
    "create_workspace",
    "destroy_workspace",
    "workspace_snapshot",
    "workspace_rollback",
    "workspace_diff",
    "workspace_status",
})

_SUBJECT_FORWARD_COMMANDS = frozenset({
    "spawn_agent",
    "terminate_agent",
    "send_message",
    "broadcast_message",
    "register_ability",
    "unregister_ability",
    "list_agents",
    "health_check",
    "delegate",
    "get_agent_info",
    "init_cluster",
    "shutdown_cluster",
    "cluster_status",
})


class SubjectService:
    """Subject 运行时编排服务。

    负责连接 Gateway，接收命令并分发给各子系统，
    将处理结果通过 Gateway 回传。

    公开接口：
    - start(): 启动服务，连接 Gateway，初始化子系统
    - stop(): 优雅关闭所有子系统
    - spawn_agent(): 通过 Gateway 创建 Agent
    - send_message(): 通过 Gateway 向 Agent 发送消息

    内部接口：
    - _handle_execute_ability(): 处理 Ability 执行命令
    - _handle_command(): 处理 persist_* 命令
    - _handle_core_event(): 处理 Core 事件
    - _handle_hitl_response(): 处理 HITL 审批响应
    - _on_hitl_promise_created(): HITL 请求广播回调
    """

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ws: Any = None
        self._running = False
        self._recv_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._pending_requests: dict[str, asyncio.Future[dict[str, Any]]] = {}

        # 子系统（在 start() 中初始化）
        self._persistence: SubjectPersistenceService | None = None
        self._ledger: ActionChainLedger | None = None
        self._workspace_mgr: WorkspaceManager | None = None
        self._hitl_notary: HITLNotary | None = None
        self._ability_runner: AbilityRunner | None = None
        self._permission_checker: PermissionChecker | None = None

    async def start(self) -> None:
        """启动服务：初始化子系统，连接 Gateway，进入消息循环。"""
        logger.info("SubjectService starting...")

        # 初始化持久化
        self._persistence = SubjectPersistenceService(db_path=self._config.db_path)
        await self._persistence.start()

        # 初始化 ActionChain 分类账
        self._ledger = ActionChainLedger(self._persistence)
        await self._ledger.start()

        # 初始化沙箱和工作区管理
        sandbox_config = SandboxExecutorConfig(
            default_timeout=self._config.gateway.command_timeout,
        )
        sandbox = SandboxExecutor(
            workspace_root=self._config.workspace_root,
            config=sandbox_config,
        )

        self._workspace_mgr = WorkspaceManager(
            root_path=self._config.workspace_root,
            sandbox=sandbox,
        )
        await self._workspace_mgr.start()

        # 初始化 HITL 子系统
        hitl_policy = HITLPolicy(
            auto_approve_abilities=self._config.hitl_policy.auto_approve_abilities,
            require_approval_by_default=self._config.hitl_policy.require_approval_by_default,
            workspace_root=self._config.hitl_policy.workspace_root
            or self._config.workspace_root,
            allowed_paths=self._config.hitl_policy.allowed_paths or None,
        )
        self._hitl_notary = HITLNotary(hitl_policy)

        # 初始化权限检查器
        self._permission_checker = PermissionChecker(
            allowed_paths=self._config.hitl_policy.allowed_paths or None,
            workspace_root=self._config.hitl_policy.workspace_root
            or self._config.workspace_root,
            require_approval=self._config.hitl_policy.require_approval_by_default,
        )

        # 初始化 AbilityRunner
        ability_config = AbilityRunnerConfig(
            hitl_timeout=self._config.gateway.command_timeout,
        )
        self._ability_runner = AbilityRunner(
            hitl_notary=self._hitl_notary,
            permission_checker=self._permission_checker,
            config=ability_config,
        )
        self._ability_runner.bind_hitl_broadcast(self._on_hitl_promise_created)
        self._ability_runner.bind_workspace_resolver(self._resolve_workspace_path)

        # 连接 Gateway
        url = self._build_gateway_url()
        try:
            self._ws = await websockets.connect(
                url,
                ping_interval=self._config.gateway.ping_interval,
            )
            self._running = True
            logger.info("SubjectService connected to Gateway at %s", url)
        except Exception as e:
            logger.error("Failed to connect to Gateway: %s", e)
            await self.stop()
            raise

        # 启动消息循环
        self._recv_task = asyncio.create_task(self._message_loop())
        logger.info("SubjectService started")

    async def stop(self) -> None:
        """优雅关闭所有子系统。"""
        logger.info("SubjectService stopping...")
        self._running = False

        # 取消所有 HITL 悬空 Promise，释放阻塞的 Future
        if self._hitl_notary is not None:
            self._hitl_notary.cancel_all_promises()

        # 取消后台任务
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        # 取消等待中的请求 Future
        for fut in self._pending_requests.values():
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()

        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None

        if self._ws is not None:
            await self._ws.close()
            self._ws = None

        if self._ledger is not None:
            await self._ledger.stop()

        if self._persistence is not None:
            await self._persistence.stop()

        if self._workspace_mgr is not None:
            await self._workspace_mgr.stop()

        logger.info("SubjectService stopped")

    def _build_gateway_url(self) -> str:
        """构造带 client_type 参数的 Gateway WebSocket URL。

        正确处理已有查询参数的 URL，避免生成双 ? 错误。
        """
        base_url = self._config.gateway.url
        parts = urlparse(base_url)
        existing_query = parts.query
        new_param = urlencode({"client_type": "subject"})
        if existing_query:
            new_query = f"{existing_query}&{new_param}"
        else:
            new_query = new_param
        new_parts = parts._replace(query=new_query)
        return urlunparse(new_parts)

    async def spawn_agent(
        self,
        name: str,
        agent_config_name: str | None = None,
        system_prompt: str = "",
        abilities: list[dict[str, Any]] | None = None,
        use_remote_executor: bool = True,
        persistence_type: str = "remote",
        gateway_url: str | None = None,
    ) -> dict[str, Any]:
        """通过 Gateway 创建 Agent。

        Args:
            name: Agent 运行时名称
            agent_config_name: agentsconfig 中的配置名称
            system_prompt: 系统提示词
            abilities: Ability 配置列表
            use_remote_executor: 是否使用远程能力执行
            persistence_type: 持久化类型
            gateway_url: Gateway WebSocket URL（Agent 分布式事件发布用）

        Returns:
            命令响应
        """
        if not self._running or self._ws is None:
            raise ConnectionError("Not connected to Gateway")

        config = AgentConfigPayload(
            name=name,
            agent_config_name=agent_config_name,
            system_prompt=system_prompt,
            gateway_url=gateway_url,
        )
        ability_defs = None
        if abilities:
            ability_defs = [
                AbilityDefinitionPayload(
                    ability_type=a["ability_type"],
                    params=a.get("params", {}),
                )
                for a in abilities
            ]

        payload: dict[str, Any] = {
            "config": config.model_dump(),
            "abilities": [a.model_dump() for a in ability_defs] if ability_defs else None,
            "use_remote_executor": use_remote_executor,
            "persistence_type": persistence_type,
        }
        request_id = generate_request_id()
        msg = GatewayMessage(
            type="spawn_agent",
            payload=payload,
            request_id=request_id,
        )
        await self._ws.send(msg.model_dump_json())

        return await self._wait_for_response(request_id, timeout=30.0)

    async def send_message(
        self,
        target: str,
        content: str,
        sender: str = "user",
    ) -> dict[str, Any]:
        """通过 Gateway 向 Agent 发送消息。

        Args:
            target: 目标 Agent 名称
            content: 消息内容
            sender: 发送者名称

        Returns:
            命令响应
        """
        if not self._running or self._ws is None:
            raise ConnectionError("Not connected to Gateway")

        payload = {
            "target": target,
            "content": content,
            "sender": sender,
        }
        request_id = generate_request_id()
        msg = GatewayMessage(
            type="send_message",
            payload=payload,
            request_id=request_id,
        )
        await self._ws.send(msg.model_dump_json())

        return await self._wait_for_response(request_id, timeout=60.0)

    async def _wait_for_response(
        self, request_id: str, timeout: float = 30.0
    ) -> dict[str, Any]:
        """等待指定 request_id 的响应。

        使用 asyncio.Future 关联请求与响应，不阻塞消息循环。
        """
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_requests[request_id] = future

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            logger.error("Request %s timed out after %.1fs", request_id, timeout)
            return {"success": False, "error": f"Request timed out after {timeout}s"}
        finally:
            self._pending_requests.pop(request_id, None)

    async def _handle_execute_ability(self, payload: dict[str, Any]) -> dict[str, Any]:
        """处理 execute_ability 命令。

        委托 AbilityRunner 执行 Ability（含 HITL 流程）。
        AbilityRunner 在需要 HITL 时会通过回调广播请求。
        """
        assert self._ability_runner is not None

        request_id = payload.get("request_id", "")
        agent_name = payload.get("agent_name", "")
        ability_name = payload.get("ability_name", "")
        tool_args = payload.get("tool_args", {})

        result = await self._ability_runner.execute_ability(
            agent_name=agent_name,
            ability_name=ability_name,
            tool_args=tool_args,
        )

        return {
            "request_id": request_id,
            "agent_name": agent_name,
            "ability_name": ability_name,
            "success": result.outcome == ActionOutcome.SUCCESS,
            "result": result.data,
            "error": result.data.get("error") if result.outcome == ActionOutcome.FAILURE else None,
        }

    async def _handle_execute_ability_and_respond(
        self, payload: dict[str, Any], request_id: str | None
    ) -> None:
        """在后台 Task 中执行 Ability 并发送结果。

        execute_ability 可能因 HITL 审批而长时间阻塞，
        因此在独立 Task 中运行，不阻塞消息循环。
        """
        try:
            result = await self._handle_execute_ability(payload)
            if self._running and self._ws is not None:
                response = GatewayMessage(
                    type="ability_result",
                    payload=result,
                    request_id=request_id,
                )
                await self._ws.send(response.model_dump_json())
        except Exception:
            logger.exception("Error in execute_ability task","request_id=%s",
                request_id,)

    async def _handle_command(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """处理 persist_* 命令。

        委托 SubjectPersistenceService 执行。
        """
        if self._persistence is None:
            return {"success": False, "error": "PersistenceService not started"}

        return await self._persistence.handle_command(command, payload)

    async def _handle_workspace_command(
        self, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """处理 workspace_* 命令。

        委托 WorkspaceManager 执行。
        """
        if self._workspace_mgr is None:
            return {"success": False, "error": "WorkspaceManager not started"}

        agent_name = payload.get("agent_name", "")

        try:
            if command == "create_workspace":
                workspace = await self._workspace_mgr.create_workspace(agent_name)
                return {"success": True, "data": {"agent_name": agent_name, "path": workspace.path}}

            elif command == "destroy_workspace":
                await self._workspace_mgr.destroy_workspace(agent_name)
                return {"success": True, "data": {"agent_name": agent_name, "destroyed": True}}

            elif command == "workspace_snapshot":
                workspace = self._workspace_mgr.get_workspace(agent_name)
                if workspace is None:
                    return {
                        "success": False,
                        "error": (
                            f"Workspace not found for"
                            f" agent '{agent_name}'"
                        ),
                    }
                message = payload.get("message", "")
                commit_hash = await workspace.snapshot(message=message)
                return {
                    "success": True,
                    "data": {
                        "agent_name": agent_name,
                        "snapshot_id": commit_hash,
                    },
                }

            elif command == "workspace_rollback":
                workspace = self._workspace_mgr.get_workspace(agent_name)
                if workspace is None:
                    return {
                        "success": False,
                        "error": (
                            f"Workspace not found for"
                            f" agent '{agent_name}'"
                        ),
                    }
                snapshot_id = payload.get("snapshot_id", "")
                await workspace.rollback(snapshot_id)
                return {
                    "success": True,
                    "data": {
                        "agent_name": agent_name,
                        "rolled_back_to": snapshot_id,
                    },
                }

            elif command == "workspace_diff":
                workspace = self._workspace_mgr.get_workspace(agent_name)
                if workspace is None:
                    return {
                        "success": False,
                        "error": (
                            f"Workspace not found for"
                            f" agent '{agent_name}'"
                        ),
                    }
                snapshot_id = payload.get("snapshot_id")
                diff_str = await workspace.diff(
                    snapshot_id=snapshot_id
                )
                return {
                    "success": True,
                    "data": {
                        "agent_name": agent_name,
                        "diff": diff_str,
                    },
                }

            elif command == "workspace_status":
                workspace = self._workspace_mgr.get_workspace(agent_name)
                if workspace is None:
                    return {
                        "success": False,
                        "error": (
                            f"Workspace not found for"
                            f" agent '{agent_name}'"
                        ),
                    }
                status = await workspace.status()
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

            else:
                return {"success": False, "error": f"Unknown workspace command: {command}"}

        except Exception as e:
            logger.exception("Error handling workspace command %s", command)
            return {"success": False, "error": str(e)}

    async def _handle_core_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """处理从 Gateway 收到的 Core 事件。"""
        if event_type == "agent_spawned":
            agent_name = payload.get("name", "")
            if agent_name and self._workspace_mgr is not None:
                try:
                    await self._workspace_mgr.create_workspace(agent_name)
                except Exception:
                    logger.exception("Failed to create workspace for %s", agent_name)
            logger.info("Agent spawned: %s", agent_name)

        elif event_type == "agent_terminated":
            agent_name = payload.get("name", "")
            if agent_name and self._workspace_mgr is not None:
                try:
                    await self._workspace_mgr.destroy_workspace(agent_name)
                except Exception:
                    logger.exception("Failed to destroy workspace for %s", agent_name)
            if self._hitl_notary is not None:
                self._hitl_notary.cancel_all_promises(agent_name)
            logger.info("Agent terminated: %s", agent_name)

        elif event_type == "action_chain_updated":
            agent_name = payload.get("agent_name", "")
            node_data = payload.get("node", {})
            if agent_name and self._ledger is not None:
                try:
                    await self._ledger.append_node(agent_name, node_data)
                except Exception:
                    logger.exception("Failed to append node for %s", agent_name)

        elif event_type == "agent_response":
            logger.info("Agent response: %s", payload.get("sender", ""))

        elif event_type == "agent_error":
            logger.error(
                "Agent error: %s agent=%s",
                payload.get("error", ""),
                payload.get("agent_name", ""),
            )

        elif event_type == "health_status":
            logger.info("Health status: %s", payload.get("status", {}))

    async def _handle_hitl_response(self, payload: dict[str, Any]) -> None:
        """处理 Observer 发来的 HITL 审批响应。

        解析审批结果，通过 HITLNotary.resolve_promise 触发
        AbilityRunner 的 await 继续执行。
        """
        assert self._hitl_notary is not None

        promise_id = payload.get("promise_id", "")
        approved = payload.get("approved", False)
        reason = payload.get("reason") or ""

        verdict = HITLVerdict(approved=approved, reason=reason)
        resolved = self._hitl_notary.resolve_promise(promise_id, verdict)

        if resolved:
            logger.info(
                "HITL response processed: promise_id=%s approved=%s",
                promise_id,
                approved,
            )
        else:
            logger.warning("HITL response for unknown/expired promise: %s", promise_id)

    async def _on_hitl_promise_created(self, promise: HITLPromise) -> None:
        """HITL Promise 创建回调：将请求广播给 Observer。

        AbilityRunner 创建 HITL Promise 后调用此回调，
        通过 Gateway WebSocket 将 hitl_request 事件发送给 Observer。
        """
        if not self._running or self._ws is None:
            logger.warning("Cannot broadcast HITL request: service not running or not connected")
            return

        hitl_payload = HITLRequestPayload(
            promise_id=promise.promise_id,
            agent_name=promise.agent_name,
            ability_name=promise.ability_name,
            tool_args=promise.tool_args,
        )
        msg = GatewayMessage(
            type=EventType.HITL_REQUEST.value,
            payload=hitl_payload.model_dump(),
        )
        await self._ws.send(msg.model_dump_json())
        logger.info("HITL request broadcasted: promise_id=%s", promise.promise_id)

    def _resolve_workspace_path(self, agent_name: str) -> str | None:
        """查询 Agent 的工作区绝对路径。

        供 AbilityRunner 在执行 Ability 前解析相对路径使用。
        工作区路径格式：workspace_root/agent_name/

        Args:
            agent_name: Agent 名称

        Returns:
            工作区绝对路径，若 Agent 无工作区则返回 None
        """
        if self._workspace_mgr is None:
            return None
        workspace = self._workspace_mgr.get_workspace(agent_name)
        if workspace is not None:
            return workspace.path
        # Agent 可能尚未创建工作区（未收到 agent_spawned 事件），
        # 但工作区目录可能已经存在于文件系统上
        ws_path = os.path.join(self._workspace_mgr.root_path, agent_name)
        if os.path.isdir(ws_path):
            return ws_path
        return None

    async def _send_gateway_message(self, msg: GatewayMessage | dict[str, Any]) -> None:
        """发送 GatewayMessage 到 Gateway WebSocket。"""
        if not self._running or self._ws is None:
            return
        if isinstance(msg, GatewayMessage):
            await self._ws.send(msg.model_dump_json())
        else:
            await self._ws.send(json.dumps(msg, ensure_ascii=False))

    async def _handle_forward_to_core(
        self, msg_type: str, payload: dict[str, Any], request_id: str | None
    ) -> None:
        """处理 Observer 转发的 Agent 管理命令。

        这些命令来自 Observer（经 Gateway 转发），Subject 需要将它们转发给 Core，
        并将 Core 的响应返回给 Observer（经 Gateway）。

        对于某些命令（如 spawn_agent），Subject 还需执行本地操作（如创建工作区），
        但工作区的创建已通过 agent_spawned 事件自动触发，无需额外处理。

        Args:
            msg_type: 命令类型
            payload: 命令载荷
            request_id: 请求 ID，用于关联响应
        """
        logger.info("Forwarding command to Core: %s (request_id=%s)", msg_type, request_id)

        cmd_msg = GatewayMessage(
            type=msg_type,
            payload=payload,
            request_id=request_id,
            client_type="subject",
        )
        await self._send_gateway_message(cmd_msg)

    async def _message_loop(self) -> None:
        """从 Gateway 接收消息并分发。

        消息类型：
        - command_result: 关联到 pending_requests 中的 Future
        - execute_ability: 在后台 Task 执行（可能阻塞等待 HITL）
        - persist_*: 直接调用 persistence
        - workspace_*: 直接调用 WorkspaceManager
        - subject_forward_commands (spawn_agent, send_message 等): 转发给 Core
        - core events: 调用 _handle_core_event
        - hitl_response: 调用 _handle_hitl_response resolve Promise
        - ping: 响应 pong
        """
        assert self._ws is not None
        async for raw in self._ws:
            if not self._running:
                break

            try:
                msg = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
                msg_type = msg.get("type", "")
                payload = msg.get("payload", {})
                request_id = msg.get("request_id")

                # 响应消息：匹配 pending_requests
                if msg_type == "command_result" and request_id:
                    future = self._pending_requests.pop(request_id, None)
                    if future is not None and not future.done():
                        future.set_result(payload)
                    continue

                # Ability 执行：后台 Task，避免 HITL 阻塞消息循环
                if msg_type == "execute_ability":
                    task = asyncio.create_task(
                        self._handle_execute_ability_and_respond(payload, request_id)
                    )
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

                # 持久化命令：直接调用
                elif msg_type in _PERSIST_COMMANDS:
                    result = await self._handle_command(msg_type, payload)
                    if self._running and self._ws is not None:
                        response = GatewayMessage(
                            type=SystemType.COMMAND_RESULT.value,
                            payload=result,
                            request_id=request_id,
                        )
                        await self._ws.send(response.model_dump_json())

                # Workspace 管理命令：直接调用
                elif msg_type in _WORKSPACE_COMMANDS:
                    result = await self._handle_workspace_command(msg_type, payload)
                    if self._running and self._ws is not None:
                        response = GatewayMessage(
                            type=SystemType.COMMAND_RESULT.value,
                            payload=result,
                            request_id=request_id,
                        )
                        await self._ws.send(response.model_dump_json())

                # Observer 转发的 Agent 管理命令：转发给 Core 并等待响应
                elif msg_type in _SUBJECT_FORWARD_COMMANDS:
                    await self._handle_forward_to_core(msg_type, payload, request_id)

                # Core 事件
                elif msg_type in _CORE_EVENT_TYPES:
                    await self._handle_core_event(msg_type, payload)

                # HITL 审批响应
                elif msg_type == "hitl_response":
                    await self._handle_hitl_response(payload)

                # Core 单体模式的 HITL 请求转发给 Observer
                elif msg_type == EventType.HITL_REQUEST.value:
                    if self._running and self._ws is not None:
                        fwd_msg = GatewayMessage(
                            type=EventType.HITL_REQUEST.value,
                            payload=payload,
                        )
                        await self._ws.send(fwd_msg.model_dump_json())

                # 心跳
                elif msg_type == SystemType.PING.value:
                    if self._running and self._ws is not None:
                        pong = GatewayMessage(type=SystemType.PONG.value)
                        await self._ws.send(pong.model_dump_json())

            except Exception:
                logger.exception("Error handling message in SubjectService")
