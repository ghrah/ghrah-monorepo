# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Agent 侧 session/branch 回执权威指针测试。

锁定 ``list_branches_result`` 的域不变量语义：``active_branch_id`` 是每个
Session 的必填属性，非活跃 Session 也直读其自身指针，不因运行态
active_session 指向别处而置空。
"""

from __future__ import annotations

from typing import Any

from ghrah.core.config import AgentConfig


def _create_agent() -> Any:
    """创建一个 ActorAgent 实例（通过 AgentBuilder）。"""
    from ghrah.agents.builder import AgentBuilder

    return AgentBuilder.from_config(AgentConfig(name="test-agent"))


class TestListBranchesResultAuthority:
    """list_branches_result 携带的 active_branch_id 必须是域权威。"""

    async def test_inactive_session_keeps_domain_active_branch_id(self) -> None:
        agent = _create_agent()
        first = await agent.create_session()
        await agent.create_session()
        # first 仍是非活跃 Session（create_session 不隐式激活）
        assert agent._context_manager.active_session_id != first.session_id

        result = agent.list_branches_result(first.session_id)

        assert result["active_branch_id"] == first.active_branch_id
        assert result["active_branch_id"] != ""
        assert {branch["branch_id"] for branch in result["branches"]} == {first.active_branch_id}

    async def test_active_session_reports_same_domain_pointer(self) -> None:
        agent = _create_agent()
        session = await agent.create_session()
        await agent.activate_session(session.session_id)

        result = agent.list_branches_result(session.session_id)

        assert result["active_branch_id"] == session.active_branch_id
        assert result["active_branch_id"] != ""

    async def test_second_session_reports_its_own_branch_domain(self) -> None:
        agent = _create_agent()
        first = await agent.create_session()
        second = await agent.create_session()
        await agent.activate_session(first.session_id)

        # 活跃的是 first，但 second 的回执仍指向 second 自己的 active branch
        result = agent.list_branches_result(second.session_id)
        assert result["active_branch_id"] == second.active_branch_id
        assert result["active_branch_id"] != first.active_branch_id
