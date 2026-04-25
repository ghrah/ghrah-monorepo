"""ghrah-subject: 控制面/执行层

Subject 是 Core 和 Observer 之间的中间层，所有 Core↔Observer 通信都经过 Subject。
在分布式模式下，Subject 端执行 Ability 并处理 HITL 裁决。
"""

from ghrah.subject.config import SubjectConfig

__all__ = ["SubjectConfig"]
