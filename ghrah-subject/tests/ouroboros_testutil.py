# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ouroboros 测试助手（阶段 2 各 test_units_* 共用）。

``wait_active`` 实现移至 ``runtime/ouroboros_bridge.py``（工厂
``mount_builtin_units`` 复用同款 ACTIVE 语义），本模块再导出以保持各测试
文件的导入路径不变。``fiber.await_()`` 只等 lifecycle task 收敛，state 迁移
可能在随后一个事件循环 tick 生效（实测 2026-08-25），故 ACTIVE 断言前
需轮询；统一 ``wait_for`` 超时，inject 名单错时表现为失败而非挂起。
"""

from __future__ import annotations

from ghrah.subject.runtime.ouroboros_bridge import wait_active

__all__ = ["wait_active"]
