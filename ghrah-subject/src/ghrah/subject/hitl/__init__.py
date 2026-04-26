"""HITL 公证处：Subject 端的 HITL 管理器。

HITLNotary 管理 HITL Promise（待审批请求），与 Core 侧的 HITLFutureStore 配对。
HITLPolicy 基于 Ability 声明和工作区路径规则判断是否需要人工审批。

分布式模式流程：
1. Subject 端执行 Ability 前通过 HITLNotary.check_request() 检查
2. HITLPolicy 判断是否需要人工审批
3. 如需审批，创建 HITLPromise 并通过 Gateway 广播给 Observer
4. Observer 审批后，resolve HITLPromise，Subject 继续执行
"""

from ghrah.subject.hitl.notary import HITLNotary, HITLPromise
from ghrah.subject.hitl.policy import HITLPolicy, HITLVerdict

__all__ = ["HITLNotary", "HITLPromise", "HITLPolicy", "HITLVerdict"]
