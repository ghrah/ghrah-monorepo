"""HITL 公证处：管理待审批的 HITL 请求，配对 Core 侧的 HITLFutureStore。

在分布式模式下，Subject 是 HITL 的裁决层：
1. AbilityRunner 执行前调用 HITLNotary.check_request()
2. HITLPolicy 判断是否需要人工审批
3. 如需审批，HITLNotary 创建 HITLPromise 并广播给 Observer
4. Observer 审批后，HITLNotary resolve 对应的 Promise
5. AbilityRunner 根据审批结果继续或终止执行
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ghrah.subject.hitl.policy import HITLPolicy, HITLVerdict

logger = logging.getLogger(__name__)

__all__ = ["HITLPromise", "HITLNotary"]


class HITLPromise:
    def __init__(
        self,
        promise_id: str,
        agent_name: str,
        ability_name: str,
        tool_args: dict[str, Any] | None = None,
        created_at: float | None = None,
        future: asyncio.Future[HITLVerdict] | None = None,
    ) -> None:
        self.promise_id = promise_id
        self.agent_name = agent_name
        self.ability_name = ability_name
        self.tool_args = tool_args or {}
        self.created_at = created_at if created_at is not None else time.time()
        if future is not None:
            self.future = future
        else:
            self.future = asyncio.get_running_loop().create_future()


class HITLNotary:
    def __init__(self, policy: HITLPolicy) -> None:
        self._policy = policy
        self._promises: dict[str, HITLPromise] = {}
        # NOTE: _counter 和 _promises 在 asyncio 单线程下安全；
        # 若未来引入多线程访问需加锁保护。
        self._counter = 0

    def check_request(
        self,
        agent_name: str,
        ability_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> HITLVerdict:
        verdict = self._policy.check_ability(ability_name, tool_args)
        if verdict.approved:
            logger.debug(
                "HITL auto-approved: agent=%s ability=%s reason=%s",
                agent_name,
                ability_name,
                verdict.reason,
            )
        else:
            logger.info(
                "HITL requires approval: agent=%s ability=%s reason=%s",
                agent_name,
                ability_name,
                verdict.reason,
            )
        return verdict

    def create_promise(
        self,
        agent_name: str,
        ability_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> HITLPromise:
        self._counter += 1
        promise_id = f"hitl-{agent_name}-{ability_name}-{self._counter}"

        # TODO: 加入超时机制 — 若 Observer 离线，Promise 将永久挂起。
        # 设计超时自动拒绝：create_promise 时注册 asyncio.wait_for 或
        # 定时器回调，超时后自动 reject_promise(reason="timeout")。
        promise = HITLPromise(
            promise_id=promise_id,
            agent_name=agent_name,
            ability_name=ability_name,
            tool_args=tool_args or {},
        )
        self._promises[promise_id] = promise
        logger.info(
            "HITL promise created: id=%s agent=%s ability=%s",
            promise_id,
            agent_name,
            ability_name,
        )
        return promise

    def resolve_promise(self, promise_id: str, verdict: HITLVerdict) -> bool:
        promise = self._promises.get(promise_id)
        if promise is None:
            logger.warning("HITL promise not found: id=%s", promise_id)
            return False

        if promise.future.done():
            logger.warning("HITL promise already resolved: id=%s", promise_id)
            return False

        promise.future.set_result(verdict)
        # TODO: resolve 后立即从 _promises 删除，无法追溯历史审批记录。
        # 若需审计日志，应在删除前将 Promise 状态持久化到 ActionChain 分类账。
        del self._promises[promise_id]
        logger.info(
            "HITL promise resolved: id=%s approved=%s",
            promise_id,
            verdict.approved,
        )
        return True

    def reject_promise(self, promise_id: str, reason: str = "") -> bool:
        verdict = HITLVerdict(approved=False, reason=reason or "rejected_by_observer")
        return self.resolve_promise(promise_id, verdict)

    def cancel_promise(self, promise_id: str) -> bool:
        promise = self._promises.get(promise_id)
        if promise is None:
            return False

        if not promise.future.done():
            promise.future.cancel()
        del self._promises[promise_id]
        logger.debug("HITL promise cancelled: id=%s", promise_id)
        return True

    def cancel_all_promises(self, agent_name: str | None = None) -> None:
        keys_to_remove: list[str] = []
        for pid, promise in self._promises.items():
            if agent_name is None or promise.agent_name == agent_name:
                if not promise.future.done():
                    promise.future.cancel()
                keys_to_remove.append(pid)

        for pid in keys_to_remove:
            del self._promises[pid]

        if keys_to_remove:
            logger.info(
                "Cancelled %d HITL promises%s",
                len(keys_to_remove),
                f" for agent {agent_name}" if agent_name else "",
            )

    def list_pending_promises(self, agent_name: str | None = None) -> list[HITLPromise]:
        if agent_name is not None:
            return [p for p in self._promises.values() if p.agent_name == agent_name]
        return list(self._promises.values())

    def get_promise(self, promise_id: str) -> HITLPromise | None:
        return self._promises.get(promise_id)

    @property
    def policy(self) -> HITLPolicy:
        return self._policy
