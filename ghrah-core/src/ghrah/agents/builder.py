# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ActorAgent 默认构造器 — AgentBuilder。

将 ActorAgent 的依赖构造逻辑从 __init__ 中分离，
提供零配置的便捷创建路径（AgentBuilder.from_config），
同时支持依赖注入的纯构造路径（ActorAgent 直接调用）。

参照 Linux task_struct 模式：内核用指针引用 mm/fs/files/signal，
而非内联逻辑。AgentBuilder 扮演内核的初始化辅助，
将子系统的构造与组合从核心结构中分离。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ghrah.abilities.executor import AbilityExecutor, LocalAbilityExecutor
from ghrah.context.manager import ContextManager
from ghrah.context.persistence import create_persistence
from ghrah.context.window import WindowManager
from ghrah.core.ability_protocol import AbilityProtocol
from ghrah.core.event_publisher import EventPublisher, NullEventPublisher
from ghrah.core.llm_protocol import LLMProtocol
from ghrah.llm.factory import LLMFactory
from ghrah.types.config_types import AgentConfig, WindowConfig

logger = logging.getLogger(__name__)


def _build_window_manager(
    config: WindowConfig,
    summary_llm_factory: Callable[[], LLMProtocol] | None = None,
) -> WindowManager:
    """从 WindowConfig 构建 WindowManager 实例。

    根据配置中的策略名称列表，创建对应的策略实例并组合到 WindowManager 中。
    ``summary_llm_factory`` 传入时，llm_summary 策略以惰性工厂回调持有 LLM 创建入口
    （首次 apply 时解析，memoize 成功结果），解除策略装配先于 LLM 创建的时序耦合。

    Args:
        config: 窗口管理配置
        summary_llm_factory: 可选的零参 LLM 工厂回调（闭包在
            ``_build_context_manager`` 处捕获 AgentConfig，见 D1 设计）

    Returns:
        配置好的 WindowManager 实例
    """
    from ghrah.chat.factory import ChatMessageFactory
    from ghrah.context.strategies.llm_summary import LLMSummaryStrategy
    from ghrah.context.strategies.sliding_window import SlidingWindowStrategy
    from ghrah.context.strategies.tool_call_fold import ToolCallFoldStrategy
    from ghrah.context.strategies.truncation import TruncationStrategy

    msg_factory = ChatMessageFactory()

    strategy_map = {
        "truncation": lambda: TruncationStrategy(),
        "sliding_window": lambda: SlidingWindowStrategy(window_size=config.sliding_window_size),
        "tool_call_fold": lambda: ToolCallFoldStrategy(
            max_content_length=config.tool_call_max_length,
            message_factory=msg_factory,
        ),
        "llm_summary": lambda: LLMSummaryStrategy(
            llm=None,
            llm_factory=summary_llm_factory,
            message_factory=msg_factory,
        ),
    }

    strategies = []
    for name in config.strategies:
        factory_fn = strategy_map.get(name)
        if factory_fn is not None:
            strategies.append(factory_fn())
        else:
            logger.warning("Unknown window strategy: %s, skipping", name)

    return WindowManager(
        strategies=strategies,
        max_tokens=config.max_tokens,
        message_factory=msg_factory,
    )


def _render_cluster_context_section(cluster_context: dict[str, Any]) -> str:
    """渲染 [Cluster Context] prompt 注入段。

    形状（截断上限已在 SupervisorActor.get_cluster_context 侧落实）：
        [Cluster Context]
        cluster_id: <id>
        members:
        - name: <name> | description: <desc> | tags: [a, b]

    Args:
        cluster_context: ``supervisor.get_cluster_context()`` 的返回

    Returns:
        渲染后的 prompt 段（不含尾随空行，由拼接方决定间距）
    """
    cluster_id = cluster_context.get("cluster_id", "")
    members = cluster_context.get("members", [])
    lines = ["[Cluster Context]", f"cluster_id: {cluster_id or 'unknown'}"]
    if members:
        lines.append("members:")
        for m in members:
            tags = ", ".join(m.get("tags", []))
            tag_part = f" | tags: [{tags}]" if tags else ""
            lines.append(
                f"- name: {m.get('name', '')} | description: {m.get('description', '')}{tag_part}"
            )
    else:
        lines.append("members: (empty cluster)")
    return "\n".join(lines)


def _build_context_manager(
    config: AgentConfig,
    persistence_factory: Callable[[AgentConfig], Any] | None = None,
    llm_factory: Callable[[AgentConfig], LLMProtocol] | None = None,
    supervisor: Any = None,
) -> ContextManager:
    """从 AgentConfig 构建 ContextManager（含 WindowManager + Persistence）。

    ``persistence_factory`` 为 per-agent 注入点：传入时以工厂构造持久化后端
    （替代默认 ``create_persistence``）；None 时维持默认行为。

    ``llm_factory`` 以零参闭包（捕获此处作用域的 AgentConfig）注入 WindowManager
    的 llm_summary 策略，供其惰性解析 LLM。

    集群身份注入（``config.cluster_context_injection=True`` 且 supervisor
    提供 ``get_cluster_context``）时，[Cluster Context] 段前置拼接
    system_prompt 头部；supervisor 不可用或缺方法 → 跳过注入 + warning
    （不阻断——structural typing 的 Subject 侧实现可能未提供该方法）。

    auto_persist 默认值（per-agent 注入语义）：``persistence_factory`` 注入
    即表达持久化意图（Subject 生产路径），无 context_config 显式声明时
    默认开启；未注入且无 context_config 时维持 False（standalone 测试
    行为不变）。context_config 提供时以其 auto_persist 为准。
    """
    from ghrah.chat.factory import ChatMessageFactory

    system_prompt = config.system_prompt
    if config.cluster_context_injection:
        get_ctx = getattr(supervisor, "get_cluster_context", None)
        if callable(get_ctx):
            try:
                section = _render_cluster_context_section(get_ctx())
                system_prompt = f"{section}\n\n{system_prompt}" if system_prompt else section
            except Exception:
                logger.warning(
                    "Cluster context injection failed for agent '%s' — skipping",
                    config.name,
                    exc_info=True,
                )
        else:
            logger.warning(
                "cluster_context_injection=True but supervisor unavailable "
                "or lacks get_cluster_context — skipping injection for '%s'",
                config.name,
            )

    window_manager = None
    if config.window is not None:
        summary_llm_factory = (lambda: llm_factory(config)) if llm_factory is not None else None
        window_manager = _build_window_manager(config.window, summary_llm_factory)

    context_config = config.context
    persistence = None
    if persistence_factory is not None:
        # per-agent 注入：工厂直接生效（替代 context 配置判定）
        persistence = persistence_factory(config)
    elif context_config is not None:
        persistence = create_persistence(
            context_config,
            agent_name=config.effective_agent_id,
        )

    message_factory = ChatMessageFactory()

    return ContextManager(
        # name 是 cluster 内可读地址；action-chain 必须按稳定 UUID 分区，
        # 否则同一 Project 的不同 cluster 中同名 agent 会覆盖彼此快照。
        agent_name=config.effective_agent_id,
        initial_state={},
        system_prompt=system_prompt,
        window_manager=window_manager,
        persistence=persistence,
        snapshot_interval=context_config.snapshot_interval if context_config else 5,
        auto_persist=(
            context_config.auto_persist
            if context_config is not None
            else persistence_factory is not None
        ),
        message_factory=message_factory,
    )


def _default_llm_factory(config: AgentConfig) -> LLMProtocol:
    """默认 LLM 工厂 — 从 agentconf 创建 ChatFormat。"""
    from agentconf import AgentsConfig

    config_client = AgentsConfig()
    resolved = config_client.resolve_agent(config.effective_agent_config_name)
    llm = LLMFactory.create(resolved)
    if config.model_overrides is not None:
        llm.apply_model_overrides(config.model_overrides)
    return llm


class AgentBuilder:
    """ActorAgent 的默认构造器 — 零配置便捷创建路径。"""

    @staticmethod
    def from_config(
        config: AgentConfig,
        abilities: list[AbilityProtocol] | None = None,
        supervisor: Any = None,
        ability_executor: AbilityExecutor | None = None,
        event_publisher: EventPublisher | None = None,
        llm_factory: Callable[[AgentConfig], LLMProtocol] | None = None,
        persistence_factory: Callable[[AgentConfig], Any] | None = None,
    ) -> Any:
        """从 AgentConfig 构建 ActorAgent（默认注入策略）。

        Args:
            config: Agent 配置
            abilities: 可选的自定义 Ability 列表。None 表示不自动注册。
            supervisor: Supervisor 引用
            ability_executor: 可选的 AbilityExecutor，默认创建 LocalAbilityExecutor
            event_publisher: 可选的 EventPublisher，默认 NullEventPublisher
            llm_factory: 可选的 LLM 工厂回调，默认从 agentconf 创建
            persistence_factory: 可选的 per-agent 持久化后端工厂
                （``(AgentConfig) -> PersistenceBackend | None``；None 走默认
                ``create_persistence``）。新 spawn 生效，存量 agent 不受影响。

        Returns:
            配置好的 ActorAgent 实例
        """
        from ghrah.agents.base import ActorAgent

        resolved_llm_factory = llm_factory or _default_llm_factory

        context_manager = _build_context_manager(
            config, persistence_factory, llm_factory=resolved_llm_factory, supervisor=supervisor
        )

        def _cm_factory() -> ContextManager:
            return _build_context_manager(
                config,
                persistence_factory,
                llm_factory=resolved_llm_factory,
                supervisor=supervisor,
            )

        if ability_executor is None:
            ability_executor = LocalAbilityExecutor(
                agent_name=config.name,
                hooks=[],
                event_publisher=event_publisher or NullEventPublisher(),
                workspace_root=config.workspace_root,
            )

        agent = ActorAgent(
            config=config,
            context_manager=context_manager,
            ability_executor=ability_executor,
            context_manager_factory=_cm_factory,
            supervisor=supervisor,
            event_publisher=event_publisher,
            llm_factory=resolved_llm_factory,
        )

        if abilities is not None:
            for ability in abilities:
                agent.register_ability(ability)

        return agent
