# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""命令 owner 表与事件订阅登记（插件挂载互斥裁决面）。

全量登记、插件侧单向互斥：所有经 bridge 挂载的命令（builtin/dynamic/
插件统一）都登记 ``command_owners``，供错误消息与协商展示；互斥裁决
（raise + exclusive）只作用于插件挂载路径——builtin 与 CoreUnit 多实例
同名共存是合法架构（serial 穿透），保持现状。

注入式设计（无全局单例）：装配链构建共享实例，经 ``mount_unit`` /
``mount_dynamic_unit`` / ``mount_builtin_units`` 可选参数传入；默认
None = 不查重（builtin 现状零改动）。
"""

from __future__ import annotations

from collections.abc import Iterable

from ghrah.plugin.errors import PluginMountError

__all__ = ["UnitRouteRegistry"]


class UnitRouteRegistry:
    """命令 owner 表 + 事件订阅登记面。

    命令互斥：插件挂载路径调用 ``register`` 前须查重（首个登记者胜，
    重复 → raise ``PluginMountError``，消息含现任 owner 名）。
    builtin 路径经 ``register_builtin`` 登记（只记名、不互斥，多实例
    同名共存合法）。事件订阅只登记不拦截（多租户合法）。
    """

    def __init__(self) -> None:
        self._command_owners: dict[str, str] = {}
        self._unit_commands: dict[str, set[str]] = {}
        self._event_subscribers: dict[str, set[str]] = {}

    def register(self, unit_name: str, commands: Iterable[str]) -> None:
        """登记 unit 的命令所有权（首个登记者胜；重复 → raise）。

        Raises:
            PluginMountError: 任一命令已被其他 unit 登记（消息含现任 owner 名）。
        """
        command_list = list(commands)
        for command in command_list:
            owner = self._command_owners.get(command)
            if owner is not None and owner != unit_name:
                raise PluginMountError(f"command '{command}' already owned by unit '{owner}'")
        self._apply(unit_name, command_list)

    def register_builtin(self, unit_name: str, commands: Iterable[str]) -> None:
        """登记 builtin/third_party 命令（只记名，不做互斥裁决）。

        builtin 与 CoreUnit 多实例同名共存合法（serial 穿透架构）；
        登记面仍如实记录，供插件挂载路径互斥查询与错误消息。
        """
        self._apply(unit_name, list(commands))

    def _apply(self, unit_name: str, commands: list[str]) -> None:
        owned = self._unit_commands.setdefault(unit_name, set())
        for command in commands:
            self._command_owners[command] = unit_name
            owned.add(command)

    def unregister(self, unit_name: str) -> None:
        """注销 unit 的全部登记（幂等：未知 unit 静默返回）。"""
        commands = self._unit_commands.pop(unit_name, None)
        if commands:
            for command in commands:
                if self._command_owners.get(command) == unit_name:
                    del self._command_owners[command]
        for event, subscribers in list(self._event_subscribers.items()):
            subscribers.discard(unit_name)
            if not subscribers:
                del self._event_subscribers[event]

    def owner_of(self, command: str) -> str | None:
        """查询命令现任 owner（未登记返回 None）。"""
        return self._command_owners.get(command)

    def subscribe_events(self, unit_name: str, event_types: Iterable[str]) -> None:
        """登记 unit 的事件订阅（只记名，不拦截）。"""
        for event_type in event_types:
            self._event_subscribers.setdefault(event_type, set()).add(unit_name)

    @property
    def event_subscribers(self) -> dict[str, set[str]]:
        """事件类型 → 订阅 unit 名集合的只读快照。"""
        return {event: set(units) for event, units in self._event_subscribers.items()}

    def command_names(self) -> list[str]:
        """已登记命令名快照（装配链预检用）。"""
        return list(self._command_owners)
