# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Cluster transport：per-cluster WS transport 句柄管理（决策 A）。

- ``manager.ClusterTransportManager``：per-cluster WS transport 管理 + init/shutdown
  转发 + 断线重连（复用 WebSocketCoreTransport 的重连机制）。
- ``handle.ClusterHandle``：单 cluster 的 Core 接入封装（spawn/terminate/list
  转发），亦作 ``ClusterHandle`` service Protocol 的具体实现。

service 契约（Protocol）定义于 :mod:`ghrah.subject.runtime.service_keys`。
"""

from __future__ import annotations

from ghrah.subject.cluster_transport.handle import ClusterHandle
from ghrah.subject.cluster_transport.manager import ClusterTransportManager

__all__ = ["ClusterHandle", "ClusterTransportManager"]
