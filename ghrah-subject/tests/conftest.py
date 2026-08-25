# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""pytest 全局配置：Ouroboros 迁移期（阶段 2）known-failures 隔离清单。

实施计划：``.kilo/plans/1787568300-ouroboros-phase2-unit-migration.md``。
规则：名单只减不增；新增红必须停下查因，不许加名单掩盖。
"""

from __future__ import annotations

# 静态隔离（装配级测试，归阶段 3.6 / MVP 项① 处置）：
# - builtin_registration：旧 register_builtin_units 装配形态，阶段 3.6 后
#   并入 test_ouroboros_assembly.py 并删除。
# - third_party_unit：第三方 unit 发现/装载经 SubjectEngine entry_points，
#   阶段 3.6 重写。
# - cluster×2：cluster_transport 留在旧基建（归项① Core Unit），重写/删除
#   归项① 吸收。
_STATIC = [
    "test_units_builtin_registration.py",
    "test_third_party_unit.py",
    "test_cluster_transport_full_profile.py",
    "test_cluster_handle_spawn_materialize.py",
]

# 暂态隔离：阶段 2 全量 unit 迁移完成（2026-08-25），清单清零、仅存静态 4。
_TRANSIENT: list[str] = []

collect_ignore = [*_STATIC, *_TRANSIENT]
