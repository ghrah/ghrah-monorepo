# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Subject unit authoring contracts（单元编写模型）。

聚合裁决后保留：SubjectUnit/UnitMeta/RouteSpec/CommandContext
（mount_unit 桥契约来源）；``UnitState`` 已删（生命周期 = Ouroboros
``FiberState``）。
"""

from ghrah.subject.unit.base import (
    CommandContext,
    CommandSource,
    RouteSpec,
    SubjectServiceKey,
    SubjectUnit,
    UnitMeta,
)

__all__ = [
    "CommandContext",
    "CommandSource",
    "RouteSpec",
    "SubjectServiceKey",
    "SubjectUnit",
    "UnitMeta",
]
