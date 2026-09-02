# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ProviderRegistry：provider 注册表 + detect 反查。

    register(provider_cls)  # 注册 provider 类型
    get(provider_type)      # 取 provider 实例（未注册 → 清晰报错）
    detect(locator)          # adopt 反查：先看 marker.provider_type，否则探测规则
                             #   （存在 .git → git；否则 → plain）

内置注册 git、plain；第三方 provider 经 register() 接入（其他 VCS/NFS/数据表
未来走此口，不动核心）。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ghrah.subject.workspace.errors import WorkspaceProviderError
from ghrah.subject.workspace.providers.base import WorkspaceProvider
from ghrah.subject.workspace.providers.git import GitWorkspaceProvider, locator_to_path
from ghrah.subject.workspace.providers.plain import PlainWorkspaceProvider

if TYPE_CHECKING:
    from ghrah.subject.sandbox.executor import SandboxExecutor

__all__ = ["ProviderRegistry", "build_default_registry"]


class ProviderRegistry:
    """provider 类型 → provider 实例的注册表。

    注册的是 provider 实例（构造时注入 SandboxExecutor 等依赖），调用方按
    provider_type 取实例。detect 按 marker 反查或文件系统探测规则分派。
    """

    def __init__(self) -> None:
        self._providers: dict[str, WorkspaceProvider] = {}

    def register(self, provider: WorkspaceProvider) -> None:
        """注册一个 provider 实例（按其 provider_type 索引）。

        重复注册同一 provider_type 会覆盖（便于测试/热替换）。
        """
        self._providers[provider.provider_type] = provider

    def get(self, provider_type: str) -> WorkspaceProvider:
        """取 provider 实例；未注册抛 WorkspaceProviderError。"""
        provider = self._providers.get(provider_type)
        if provider is None:
            raise WorkspaceProviderError(f"Unknown workspace provider type: {provider_type!r}")
        return provider

    def has(self, provider_type: str) -> bool:
        """provider_type 是否已注册。"""
        return provider_type in self._providers

    def types(self) -> list[str]:
        """已注册的 provider_type 列表。"""
        return list(self._providers.keys())

    def detect(self, locator: str) -> WorkspaceProvider | None:
        """按 marker 反查 provider_type；无 marker 时按探测规则
        （存在 .git → git；否则 → plain）。

        非文件系统 locator 探测规则未定义（MVP 不实现），返回 None。
        """
        from ghrah.subject.workspace.marker import read_marker

        # file:// locator 才能做文件系统探测
        try:
            ws_path = locator_to_path(locator)
        except ValueError:
            return None

        marker = read_marker(ws_path)
        if marker is not None:
            provider = self._providers.get(marker.provider_type)
            if provider is not None:
                return provider
            # marker 声明的 provider_type 未注册 → 退化到探测规则
        if os.path.isdir(os.path.join(ws_path, ".git")):
            return self._providers.get("git")
        if os.path.isdir(ws_path) or os.path.lexists(ws_path):
            return self._providers.get("plain")
        # 目录不存在：默认 plain（init 时创建）
        return self._providers.get("plain")


def build_default_registry(sandbox: SandboxExecutor) -> ProviderRegistry:
    """构造内置 git + plain 的默认注册表。"""
    registry = ProviderRegistry()
    registry.register(GitWorkspaceProvider(sandbox))
    registry.register(PlainWorkspaceProvider())
    return registry
