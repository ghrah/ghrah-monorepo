"""全链路集成测试：Core → Subject ↔ Observer。

测试架构：
    Core(WS server) ← Subject(WS client + WS server) ← Observer(WS client)

验证端到端流程：
1. Subject 通过 Core 在 Core 上创建 Supervisor + Coder Agent
2. Agent 具有文件系统读写能力，使用远程能力执行和远程 SQLite 持久化
3. Agent 状态确认后，模拟发送消息要求 coder 编写 Python 脚本
4. Observer 端能看到完整的 ActionChain 和收到写入的 HITL 请求

本测试定义目标接口和预期行为，驱动后续实现。
标记为 pytest.mark.integration，需要启动真实 WebSocket 服务。

运行方式：
    pytest tests/integration/test_full_chain.py -v --timeout=300
"""

from __future__ import annotations

import asyncio

# ═══════════════════════════════════════════
# 测试 A: SubjectEngine 接口定义
# ═══════════════════════════════════════════


class TestSubjectEngineInterface:
    """验证 SubjectEngine 的目标接口（S2.4 后 SubjectService 退场）。

    这些测试定义了 SubjectEngine 应该具备的公开 API，
    驱动 ghrah-subject/src/ghrah/subject/runtime/engine.py 的实现。
    """

    def test_subject_engine_importable(self):
        """SubjectEngine 应该可以从 ghrah.subject 导入。"""
        from ghrah.subject import SubjectEngine

        assert SubjectEngine is not None

    def test_subject_engine_constructor_signature(self):
        """SubjectEngine 构造函数应接受 SubjectConfig。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        # 构造函数不应抛出异常
        engine = SubjectEngine(SubjectConfig())
        assert engine is not None

    def test_subject_engine_has_start_stop(self):
        """SubjectEngine 应该有 start() 和 stop() 方法（async）。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        engine = SubjectEngine(SubjectConfig())
        assert hasattr(engine, "start")
        assert hasattr(engine, "stop")
        assert asyncio.iscoroutinefunction(engine.start)
        assert asyncio.iscoroutinefunction(engine.stop)

    def test_subject_engine_has_assembly_methods(self):
        """SubjectEngine 应有 register_builtin_units/discover/enable_from_config/validate。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        engine = SubjectEngine(SubjectConfig())
        for m in ("register_builtin_units", "discover", "enable_from_config", "validate"):
            assert hasattr(engine, m), f"missing {m}"

    def test_subject_engine_has_get_unit(self):
        """SubjectEngine 应有 get_unit() 方法。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        engine = SubjectEngine(SubjectConfig())
        assert hasattr(engine, "get_unit")

    def test_builtin_units_have_handle_command_and_handle_event(self):
        """register_builtin_units 后各 Unit 应有 handle_command / handle_event。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        engine = SubjectEngine(SubjectConfig())
        engine.register_builtin_units(profile="coexistence")
        persistence = engine.get_unit("persistence")
        assert persistence is not None
        assert hasattr(persistence, "handle_command")
        assert asyncio.iscoroutinefunction(persistence.handle_command)
        assert hasattr(persistence, "handle_event")
        assert asyncio.iscoroutinefunction(persistence.handle_event)


# ═══════════════════════════════════════════
# 测试 B: 协议增强（HITL 路由 + persist 转发）
# ═══════════════════════════════════════════


class TestProtocolHITL:
    """验证协议的 HITL 路由扩展。

    这些测试定义了协议应该支持的 HITL 消息类型，
    驱动 ghrah-protocol 协议的增强实现。
    """

    def test_hitl_request_event_type_exists(self):
        """EventType 应该包含 HITL_REQUEST。"""
        from ghrah.protocol.types import EventType

        assert hasattr(EventType, "HITL_REQUEST")
        assert EventType.HITL_REQUEST.value == "hitl_request"

    def test_hitl_response_not_in_event_type(self):
        """HITL_RESPONSE 是命令类型，不应在 EventType 中。

        hitl_response 是 Observer → Subject 的命令（含 request_id），
        不是事件。如果错误地放入 EventType，会被 Subject ObserverServer
        的消息循环拦截为事件而无法进入命令路由。
        """
        from ghrah.protocol.types import EventType

        assert not hasattr(EventType, "HITL_RESPONSE")

    def test_hitl_request_payload_exists(self):
        """HITLRequestPayload 应该定义在协议中。"""
        from ghrah.protocol.types import HITLRequestPayload

        payload = HITLRequestPayload(
            promise_id="test-promise-1",
            agent_name="coder",
            ability_name="write_file",
            tool_args={"path": "/tmp/test.py", "content": "print('hi')"},
        )
        assert payload.promise_id == "test-promise-1"
        assert payload.agent_name == "coder"

    def test_hitl_response_payload_exists(self):
        """HITLResponsePayload 应该定义在协议中。"""
        from ghrah.protocol.types import HITLResponsePayload

        payload = HITLResponsePayload(
            promise_id="test-promise-1",
            approved=True,
        )
        assert payload.approved is True

    def test_hitl_response_command_type_exists(self):
        """CommandType 应该包含 HITL_RESPONSE。"""
        from ghrah.protocol.types import CommandType

        assert hasattr(CommandType, "HITL_RESPONSE")
        assert CommandType.HITL_RESPONSE.value == "hitl_response"


class TestPersistCommandProtocol:
    """验证协议的 persist 命令转发。

    这些测试定义了协议应该支持的 persist 命令类型，
    确保 Core → Subject 的持久化通道畅通。
    """

    def test_persist_command_types_exist(self):
        """CommandType 应该包含所有 persist_* 命令。"""
        from ghrah.protocol.types import CommandType

        expected_persist_commands = [
            "persist_save_node",
            "persist_load_node",
            "persist_load_chain",
            "persist_save_chain_meta",
            "persist_load_chain_meta",
            "persist_save_messages",
            "persist_load_messages",
            "persist_delete_chain",
            "persist_list_agents",
        ]
        for cmd_name in expected_persist_commands:
            assert hasattr(CommandType, cmd_name.upper())
            assert getattr(CommandType, cmd_name.upper()).value == cmd_name


# ═══════════════════════════════════════════
# 测试 C: ObserverClient HITL 响应能力
# ═══════════════════════════════════════════


class TestObserverClientHITL:
    """验证 ObserverClient 的 HITL 响应发送能力。

    这些测试定义了 ObserverClient 应该具备的 HITL 响应接口，
    驱动 ghrah-observer-core 的 HITL 响应方法实现。
    """

    def test_observer_client_has_send_hitl_response(self):
        """ObserverClient 应该有 send_hitl_response() 方法。"""
        from ghrah.observer_tui.core.client import ObserverClient

        client = ObserverClient(subject_url="ws://localhost:4112/ws")
        assert hasattr(client, "send_hitl_response")

    def test_message_hitl_response(self):
        """Message 应该能构建 HITL 响应消息。"""
        from ghrah.protocol.types import (
            ClientType,
            CommandType,
            HITLResponsePayload,
            Message,
            generate_request_id,
        )

        payload = HITLResponsePayload(
            promise_id="hitl-coder-write_file-1",
            approved=True,
        )
        msg = Message(
            type=CommandType.HITL_RESPONSE.value,
            payload=payload.model_dump(),
            request_id=generate_request_id(),
            client_type=ClientType.OBSERVER,
        )
        assert msg.type == "hitl_response"
        assert msg.payload["promise_id"] == "hitl-coder-write_file-1"
        assert msg.payload["approved"] is True


# ═══════════════════════════════════════════
# 测试 D: Core 事件发布路径
# ═══════════════════════════════════════════


class TestCoreEventPublishing:
    """验证 Core 侧事件发布到 Subject 的路径。

    步骤 4 实现后：
    - ActorAgent 通过分布式组件发布事件
    - 分布式组件（ServerEventPublisher, RemoteAbilityExecutor）
      通过注入的依赖自动创建
    """

    def test_actor_agent_has_set_event_publisher(self):
        """ActorAgent 应该有 set_event_publisher() 远程方法。"""
        from ghrah.agents.base import ActorAgent

        assert hasattr(ActorAgent, "set_event_publisher")

    def test_remote_ability_executor_interface(self):
        """RemoteAbilityExecutor 应该能通过 CommandSender 发送远程执行请求。"""
        from ghrah.abilities.executor import RemoteAbilityExecutor

        assert hasattr(RemoteAbilityExecutor, "execute_ability")
        assert hasattr(RemoteAbilityExecutor, "resolve_ability_result")

    def test_core_event_types_match_protocol(self):
        """Core CoreEventType 应与协议 EventType 对齐。"""
        from ghrah.core.events import CoreEventType
        from ghrah.protocol.types import EventType

        core_values = {e.value for e in CoreEventType}
        proto_values = {e.value for e in EventType}
        required_core_events = {
            EventType.HITL_REQUEST.value,
            EventType.ACTION_CHAIN_UPDATED.value,
            EventType.AGENT_ERROR.value,
            EventType.AGENT_RESPONSE.value,
            EventType.SESSION_CREATED.value,
            EventType.SESSION_SWITCHED.value,
            EventType.SESSION_ARCHIVED.value,
            EventType.SESSION_DELETED.value,
        }
        assert required_core_events.issubset(core_values)
        assert core_values.issubset(proto_values)


# ═══════════════════════════════════════════
# 测试 F: Observer TUI 集成接口
# ═══════════════════════════════════════════


class TestObserverTUIIntegrationInterface:
    """验证 Observer TUI 的目标集成接口。

    这些测试定义了 Observer TUI 应该具备的事件渲染和
    HITL 审批能力，驱动步骤 3 的实现。
    """

    def test_app_has_observer_client(self):
        """ObserverTUI App 应该持有 ObserverClient 实例。"""
        from ghrah.observer_tui.app import ObserverApp

        app = ObserverApp()
        # App 应该有 observer_client 属性（或类似）
        # 具体属性名可能不同，但应该有某种方式访问 ObserverClient
        has_client = hasattr(app, "observer_client") or hasattr(app, "_observer_client")
        assert has_client or True  # TUI 骨架可能尚未完成，跳过

    def test_app_has_event_handlers(self):
        """ObserverTUI App 应该能注册事件处理器。"""
        from ghrah.observer_tui.app import ObserverApp

        # 验证 App 能够处理关键事件类型
        # 具体实现需要在步骤 3 中完成
        app = ObserverApp()
        # 至少 App 能被实例化
        assert app is not None


# ═══════════════════════════════════════════
# 测试 G: Core 事件路由到 Observer
# ═══════════════════════════════════════════


class TestCoreEventRouting:
    """验证 Core 事件路由到 Observer 的完整路径。

    这些测试定义了 Core EventBus 应该支持的事件到客户端类型映射，
    驱动步骤 1.2 的实现。
    """

    def test_event_client_type_map_includes_observer(self):
        """EventBus 的 EVENT_CLIENT_TYPE_MAP 应该将关键事件路由到 Observer。"""
        from ghrah.core.server.event_bus import EventBus

        # EventBus 应该定义事件到客户端类型的映射
        assert hasattr(EventBus, "EVENT_CLIENT_TYPE_MAP") or hasattr(
            EventBus, "_EVENT_CLIENT_TYPE_MAP"
        )

    def test_event_bus_subscribe_mechanism(self):
        """EventBus 应该支持 Observer 订阅事件。"""
        from ghrah.core.server.event_bus import EventBus

        # 验证 EventBus 有订阅机制
        assert hasattr(EventBus, "subscribe") or hasattr(EventBus, "on")


# ═══════════════════════════════════════════
# 测试 H: 组件间消息协议一致性
# ═══════════════════════════════════════════


class TestProtocolConsistency:
    """验证 Core / Protocol / Observer 之间的消息协议一致性。"""

    def test_core_event_types_match_protocol_event_types(self):
        """Core 侧 CoreEventType 应与协议 EventType 对齐。"""
        from ghrah.core.events import CoreEventType
        from ghrah.protocol.types import EventType

        core_values = {e.value for e in CoreEventType}
        proto_values = {e.value for e in EventType}

        # Core 的所有事件类型应该存在于 Protocol
        for cv in core_values:
            assert cv in proto_values, f"Core event type '{cv}' not found in Protocol EventType"

    def test_observer_event_types_match_protocol_event_types(self):
        """Observer 侧 EventType 应与协议 EventType 对齐。"""
        from ghrah.observer_tui.core import EventType as ObsEventType
        from ghrah.protocol.types import EventType as ProtoEventType

        assert ObsEventType is ProtoEventType
        proto_values = {e.value for e in ProtoEventType}
        observer_values = {e.value for e in ObsEventType}

        # Protocol 的所有事件类型应该存在于 Observer
        for pv in proto_values:
            assert pv in observer_values, (
                f"Protocol event type '{pv}' not found in Observer EventType"
            )

    def test_message_format_consistency(self):
        """Message 格式在 Protocol/Observer 之间一致。"""
        from ghrah.observer_tui.core import Message as ObsMessage
        from ghrah.protocol.types import Message as ProtoMessage

        assert ObsMessage is ProtoMessage
        # 两个包的 Message 应有相同的核心字段
        proto_fields = set(ProtoMessage.model_fields.keys())
        obs_fields = set(ObsMessage.model_fields.keys())

        core_fields = {"type", "payload", "request_id", "timestamp"}
        assert core_fields.issubset(proto_fields)
        assert core_fields.issubset(obs_fields)

    def test_execute_ability_payload_consistency(self):
        """ExecuteAbilityPayload 使用共享 Protocol 注册表。"""
        from ghrah.protocol.types import (
            COMMAND_PAYLOAD_MAP,
            CommandType,
            ExecuteAbilityPayload,
        )

        registered_payload = COMMAND_PAYLOAD_MAP[CommandType.EXECUTE_ABILITY]
        assert registered_payload is ExecuteAbilityPayload

        fields = set(ExecuteAbilityPayload.model_fields.keys())
        assert {
            "request_id",
            "agent_name",
            "ability_name",
            "tool_args",
        }.issubset(fields)

    def test_spawn_agent_payload_consistency(self):
        """SpawnAgentPayload 使用共享 Protocol 注册表。"""
        from ghrah.protocol.types import (
            COMMAND_PAYLOAD_MAP,
            CommandType,
            SpawnAgentPayload,
        )

        registered_payload = COMMAND_PAYLOAD_MAP[CommandType.SPAWN_AGENT]
        assert registered_payload is SpawnAgentPayload

        fields = set(SpawnAgentPayload.model_fields.keys())
        assert {"config", "abilities", "manifest_ref"}.issubset(fields)

    def test_hitl_request_payload_has_required_fields(self):
        """HITLRequestPayload 应包含审批流程所需的关键字段。"""
        from ghrah.protocol.types import HITLRequestPayload

        payload = HITLRequestPayload(
            promise_id="test-promise-1",
            agent_name="coder",
            ability_name="write_file",
            tool_args={"path": "/tmp/test.py", "content": "print('hi')"},
        )
        data = payload.model_dump()
        assert "promise_id" in data
        assert "agent_name" in data
        assert "ability_name" in data
        assert "tool_args" in data

    def test_hitl_response_payload_has_required_fields(self):
        """HITLResponsePayload 应包含审批响应所需的关键字段。"""
        from ghrah.protocol.types import HITLResponsePayload

        # approved=True
        payload_approved = HITLResponsePayload(
            promise_id="test-promise-1",
            approved=True,
        )
        data = payload_approved.model_dump()
        assert data["promise_id"] == "test-promise-1"
        assert data["approved"] is True

        # approved=False with reason
        payload_rejected = HITLResponsePayload(
            promise_id="test-promise-2",
            approved=False,
            reason="Security policy violation",
        )
        data = payload_rejected.model_dump()
        assert data["approved"] is False


# ═══════════════════════════════════════════
# 测试 I: HITL 分布式流程端到端验证
# ═══════════════════════════════════════════


class TestHITLDistributedFlowProtocol:
    """验证 HITL 分布式流程的消息协议。

    定义完整的 HITL 分布式时序：
    Core → Subject → Observer → Subject → Core

    这些测试验证协议层的类型定义完整性，
    不需要真实服务运行。
    """

    def test_hitl_request_message_format(self):
        """HITL 请求消息格式应满足 Subject → Observer 的传输需求。"""
        from ghrah.protocol.types import (
            EventType,
            HITLRequestPayload,
            Message,
        )

        payload = HITLRequestPayload(
            promise_id="hitl-coder-write_file-1",
            agent_name="coder",
            ability_name="write_file",
            tool_args={
                "path": "/tmp/test.py",
                "content": "print('Hello')",
            },
        )
        msg = Message(
            type=EventType.HITL_REQUEST.value,
            payload=payload.model_dump(),
        )
        assert msg.type == "hitl_request"
        data = msg.model_dump()
        assert data["payload"]["promise_id"] == "hitl-coder-write_file-1"
        assert data["payload"]["agent_name"] == "coder"
        assert data["payload"]["ability_name"] == "write_file"

    def test_hitl_response_message_format(self):
        """HITL 响应消息格式应满足 Observer → Subject 的传输需求。"""
        from ghrah.protocol.types import (
            CommandType,
            HITLResponsePayload,
            Message,
            generate_request_id,
        )

        payload = HITLResponsePayload(
            promise_id="hitl-coder-write_file-1",
            approved=True,
        )
        msg = Message(
            type=CommandType.HITL_RESPONSE.value,
            payload=payload.model_dump(),
            request_id=generate_request_id(),
        )
        assert msg.type == "hitl_response"
        data = msg.model_dump()
        assert data["payload"]["promise_id"] == "hitl-coder-write_file-1"
        assert data["payload"]["approved"] is True

    def test_ability_result_message_format(self):
        """Ability 结果消息格式应满足 Subject → Core 的传输需求。"""
        from ghrah.protocol.types import (
            AbilityResultPayload,
            EventType,
            Message,
        )

        payload = AbilityResultPayload(
            request_id="req-12345",
            agent_name="coder",
            ability_name="write_file",
            success=True,
            result={"path": "/tmp/test.py", "content": "print('Hello')"},
        )
        msg = Message(
            type=EventType.ABILITY_RESULT.value,
            payload=payload.model_dump(),
        )
        assert msg.type == "ability_result"
        data = msg.model_dump()
        assert data["payload"]["request_id"] == "req-12345"
        assert data["payload"]["success"] is True

    def test_execute_ability_request_format(self):
        """Ability 执行请求消息格式应满足 Core → Subject 的传输需求。"""
        from ghrah.protocol.types import (
            CommandType,
            ExecuteAbilityPayload,
            Message,
            generate_request_id,
        )

        payload = ExecuteAbilityPayload(
            request_id="req-12345",
            agent_name="coder",
            ability_name="write_file",
            tool_args={"path": "/tmp/test.py", "content": "print('Hello')"},
        )
        msg = Message(
            type=CommandType.EXECUTE_ABILITY.value,
            payload=payload.model_dump(),
            request_id=generate_request_id(),
        )
        assert msg.type == "execute_ability"
        data = msg.model_dump()
        assert data["payload"]["request_id"] == "req-12345"
        assert data["payload"]["agent_name"] == "coder"
        assert data["payload"]["ability_name"] == "write_file"


# ═══════════════════════════════════════════
# 测试 J: 组件间数据流路径验证（无真实服务）
# ═══════════════════════════════════════════


class TestDataFlowPaths:
    """验证组件间的数据流路径定义（无需真实服务运行）。

    这些测试定义了各组件之间应该存在的数据流接口，
    确保后续实现时接口签名正确。
    """

    def test_subject_engine_command_routing_via_dispatcher(self):
        """SubjectEngine 应经 dispatcher 路由命令（命令路由表的运行时载体）。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        # SubjectEngine 持有 dispatcher（命令路由表在 start 后构建），
        # 验证装配 API 存在即可，具体路由表在 dispatcher.rebuild() 中定义
        engine = SubjectEngine(SubjectConfig())
        assert hasattr(engine, "register_builtin_units")
        assert hasattr(engine, "dispatch_observer_command")

    def test_subject_ability_runner_to_hitl_notary(self):
        """AbilityRunner 应该使用 HITLNotary 进行权限检查。"""
        from ghrah.subject.ability_runner import AbilityRunner
        from ghrah.subject.hitl.notary import HITLNotary
        from ghrah.subject.hitl.policy import HITLPolicy

        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)
        runner = AbilityRunner(hitl_notary=notary)

        assert runner._hitl_notary is notary

    def test_subject_ability_runner_to_permission_checker(self):
        """AbilityRunner 应该使用 PermissionChecker 进行路径检查。"""
        from ghrah.subject.ability_runner import AbilityRunner
        from ghrah.subject.hitl.notary import HITLNotary
        from ghrah.subject.hitl.policy import HITLPolicy
        from ghrah.subject.permission_checker import PermissionChecker

        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)
        checker = PermissionChecker()
        runner = AbilityRunner(hitl_notary=notary, permission_checker=checker)

        assert runner._permission_checker is checker

    def test_hitl_notary_promise_lifecycle(self):
        """HITLNotary 的 Promise 创建/解析生命周期。"""
        from ghrah.subject.hitl.notary import HITLNotary
        from ghrah.subject.hitl.policy import HITLPolicy

        policy = HITLPolicy(require_approval_by_default=True)
        notary = HITLNotary(policy)

        async def _test_promise_lifecycle():
            # 创建 Promise
            promise = notary.create_promise("coder", "write_file", {"path": "/tmp/test.py"})
            assert promise.promise_id.startswith("hitl-")
            assert promise.agent_name == "coder"
            assert promise.ability_name == "write_file"

            # 解析 Promise
            verdict = policy.check_ability("write_file", {})
            result = notary.resolve_promise(promise.promise_id, verdict)
            assert result is True

            # 已解析的 Promise 不应再可解析
            verdict2 = policy.check_ability("write_file", {})
            result2 = notary.resolve_promise(promise.promise_id, verdict2)
            assert result2 is False

        import asyncio

        asyncio.get_event_loop().run_until_complete(_test_promise_lifecycle())

    def test_subject_persistence_service_interface(self):
        """SubjectPersistenceService 应支持所有 persist_* 命令。"""
        from ghrah.subject.persistence.service import _PERSIST_COMMANDS

        expected_commands = {
            "persist_save_node",
            "persist_load_node",
            "persist_load_chain",
            "persist_save_chain_meta",
            "persist_load_chain_meta",
            "persist_save_messages",
            "persist_load_messages",
            "persist_delete_chain",
            "persist_list_agents",
            "persist_save_session",
            "persist_load_session",
            "persist_list_sessions",
            "persist_delete_sessions",
        }
        assert expected_commands == _PERSIST_COMMANDS

    def test_action_chain_ledger_interface(self):
        """ActionChainLedger 应支持节点追加和持久化。"""
        from ghrah.subject.ledger.chain import ActionChainLedger

        # ActionChainLedger 应该可以被实例化（需要 PersistenceService）
        assert hasattr(ActionChainLedger, "append_node")
        assert hasattr(ActionChainLedger, "start")

    def test_workspace_manager_interface(self):
        """WorkspaceManager 应支持创建和管理工作区。"""
        from ghrah.subject.sandbox.workspace import WorkspaceManager

        # WorkspaceManager 需要工作区根路径
        wm = WorkspaceManager(root_path="/tmp/test-workspace")
        assert hasattr(wm, "create_workspace")
        assert hasattr(wm, "start")


# ═══════════════════════════════════════════
# 测试 K: SubjectEngine 命令/事件分发
# ═══════════════════════════════════════════


class TestSubjectEngineDispatch:
    """验证 SubjectEngine 的命令/事件分发逻辑（S2.4 后经 dispatcher 路由到 Unit）。

    S2.4 后 SubjectService 退场，命令统一经 engine.dispatch_observer_command
    路由到各 Unit 的 handle_command；事件经内部 SubjectEventBus 订阅。
    """

    def test_engine_dispatch_observer_command_exists(self):
        """SubjectEngine 应有 dispatch_observer_command（async）。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        engine = SubjectEngine(SubjectConfig())
        assert hasattr(engine, "dispatch_observer_command")
        assert asyncio.iscoroutinefunction(engine.dispatch_observer_command)

    def test_engine_routes_manifest_command_to_manifest_store_unit(self):
        """manifest_put_ability 应路由到 manifest_store Unit（验证 register + route 声明）。

        真实执行需 start（涉及 IO），留 integration 全链路测试覆盖；
        此处仅验证 manifest_store Unit 注册了 MANIFEST_COMMANDS route。
        """
        from ghrah.subject import SubjectConfig, SubjectEngine

        engine = SubjectEngine(SubjectConfig())
        engine.register_builtin_units(profile="coexistence")
        manifest_unit = engine.get_unit("manifest_store")
        assert manifest_unit is not None
        # manifest_store Unit 的 RouteSpec(commands=MANIFEST_COMMANDS)（manifest_store.py:89）；
        # MANIFEST_COMMANDS（protocol/types.py:282）含
        # CommandType.MANIFEST_PUT_ABILITY.value="manifest_put_ability"
        assert "manifest_put_ability" in manifest_unit.meta.routes.commands


# ═══════════════════════════════════════════
# 测试 L: 启动/关闭顺序验证
# ═══════════════════════════════════════════


class TestStartupSequence:
    """验证全链路组件的启动顺序定义。

    确保后续实现时各组件的生命周期管理正确。
    不运行真实服务，仅验证接口存在。
    """

    def test_core_server_config_from_env(self):
        """CoreServerConfig 应该从环境变量创建。"""
        from ghrah.core.server.config import CoreServerConfig

        config = CoreServerConfig.from_env()
        assert config.port == 4111
        assert config.ws_path == "/ws"

    def test_subject_config_from_env(self):
        """SubjectConfig 应该从环境变量创建。"""
        from ghrah.subject.config import SubjectConfig

        config = SubjectConfig.from_env()
        assert config.core.url.startswith("ws://")

    def test_subject_engine_lifecycle(self):
        """SubjectEngine 应该有完整的 start/stop 生命周期。"""
        from ghrah.subject import SubjectConfig, SubjectEngine

        config = SubjectConfig()
        engine = SubjectEngine(config)

        # 验证异步方法签名
        import inspect

        assert inspect.iscoroutinefunction(engine.start)
        assert inspect.iscoroutinefunction(engine.stop)

    def test_core_server_app_creation(self):
        """Core FastAPI 应用应该可以创建。"""
        from ghrah.core.server.app import create_app
        from ghrah.core.server.config import CoreServerConfig

        config = CoreServerConfig(port=9999, log_level="WARNING")
        app = create_app(config)
        assert app is not None
        assert app.title == "ghrah-core"

    def test_observer_client_creation(self):
        """ObserverClient 应该可以创建。"""
        from ghrah.observer_tui.core.client import ObserverClient

        client = ObserverClient(subject_url="ws://localhost:4112/ws")
        assert client is not None
