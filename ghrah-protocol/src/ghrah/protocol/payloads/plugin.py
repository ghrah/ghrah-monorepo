# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""Plugin 域载荷模型（协商命令与插件事件）。

协商 wire 形状复用 ghrah-plugin 的 negotiator 模型（单一权威）：
``PluginNegotiateResultPayload`` 是 ``NegotiationResult`` 的空体子类，
序列化形状与 negotiator 纯函数输出逐位一致，零字段重复。
``plugin_negotiated`` 是纯重协商信号（Observer 收到后重发 plugin_negotiate），
不携带全量协商结果。
"""

from __future__ import annotations

from ghrah.plugin.negotiator import NegotiationResult, TsHalfReport
from pydantic import BaseModel, Field

__all__ = [
    "PluginCrashedPayload",
    "PluginLifecyclePayload",
    "PluginNegotiatedPayload",
    "PluginNegotiatePayload",
    "PluginNegotiateResultPayload",
]


class PluginNegotiatePayload(BaseModel):
    """plugin_negotiate 命令载荷（Observer → Subject：TS 半已启用清单）。"""

    enabled_ts: list[TsHalfReport] = Field(default_factory=list)


class PluginNegotiateResultPayload(NegotiationResult):
    """plugin_negotiate 命令响应载荷（command_result.data；形状 = negotiator 输出）。"""


class PluginLifecyclePayload(BaseModel):
    """plugin_enabled / plugin_disabled 事件载荷。"""

    plugin_id: str
    version: str
    instance_ids: list[str] = Field(default_factory=list)


class PluginNegotiatedPayload(BaseModel):
    """plugin_negotiated 事件载荷（变更级重协商信号，变更涉及的 plugin_id 清单）。"""

    changed: list[str] = Field(default_factory=list)


class PluginCrashedPayload(BaseModel):
    """plugin_crashed 事件载荷（插件命令 handler 运行期异常，自动卸载后广播）。"""

    plugin_id: str
    command: str
    error: str
    instance_id: str | None = None
