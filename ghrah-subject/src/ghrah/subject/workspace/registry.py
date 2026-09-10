# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ProviderRegistry：provider 注册表 + detect 反查。

    register(provider)     # 注册 provider 实例
    get(provider_type)     # 取 provider 实例（未注册 → 清晰报错）
    detect(locator)        # file:// 可解析 → plain；否则 None

挂载语义下内置仅注册 plain（legacy git provider 已移除）。第三方 provider
经 register() 接入（其他后端未来走此口，不动核心）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ghrah.subject.workspace.errors import WorkspaceProviderError
from ghrah.subject.workspace.locator import locator_to_path
from ghrah.subject.workspace.providers.base import WorkspaceProvider
from ghrah.subject.workspace.providers.plain import PlainWorkspaceProvider

if TYPE_CHECKING:
    from ghrah.subject.sandbox.executor import SandboxExecutor

__all__ = ["ProviderRegistry", "build_default_registry"]


class ProviderRegistry:
    """provider 类型 → provider 实例的注册表。

    注册的是 provider 实例（构造时注入 SandboxExecutor 等依赖），调用方按
    provider_type 取实例。detect 按 locator 可解析性分派。
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
        """file:// locator 可解析出本地路径 → plain；否则 None。

        挂载语义下不探测目录内容（含 .git 状态一律不看）——注册面零物理
        操作，provider 分派只依赖 locator 本身。
        """
        try:
            locator_to_path(locator)
        except ValueError:
            return None
        return self._providers.get("plain")


def build_default_registry(sandbox: SandboxExecutor) -> ProviderRegistry:
    """构造内置 plain 的默认注册表。

    Args:
        sandbox: SandboxExecutor（保留参数以维持既有装配签名；plain provider
            当前不需要它）。
    """
    _ = sandbox
    registry = ProviderRegistry()
    registry.register(PlainWorkspaceProvider())
    return registry
