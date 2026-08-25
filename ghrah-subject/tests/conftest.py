# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""pytest 全局配置。

Ouroboros 合并装配层（1787622968763）实施后隔离清单清零：
旧基建（SubjectEngine 装配/cluster_transport/transport 三件套）与
四件套（ability_runner/hitl_policy/hitl_notary/persistence）测试
随源码删除；third_party_unit 重写为 ctx 挂载形态。无已知失败豁免。
"""

from __future__ import annotations

collect_ignore: list[str] = []
