# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""UnitRouteRegistry 语义测试：首登/重复 raise（含 owner 名）/幂等注销/
owner 查询/事件多订阅共存/builtin 登记不互斥。"""

from __future__ import annotations

import pytest
from ghrah.plugin.errors import PluginMountError

from ghrah.subject.runtime.route_registry import UnitRouteRegistry


def test_first_registration_wins() -> None:
    registry = UnitRouteRegistry()
    registry.register("plugin-a", ["foo", "bar"])
    assert registry.owner_of("foo") == "plugin-a"
    assert registry.owner_of("bar") == "plugin-a"
    assert registry.owner_of("missing") is None
    assert sorted(registry.command_names()) == ["bar", "foo"]


def test_duplicate_command_raises_with_owner_name() -> None:
    registry = UnitRouteRegistry()
    registry.register("plugin-a", ["foo"])
    with pytest.raises(PluginMountError) as excinfo:
        registry.register("plugin-b", ["foo", "other"])
    assert "command 'foo' already owned by unit 'plugin-a'" in str(excinfo.value)
    # 失败的登记不部分生效
    assert registry.owner_of("other") is None


def test_same_unit_re_register_is_idempotent() -> None:
    registry = UnitRouteRegistry()
    registry.register("plugin-a", ["foo"])
    registry.register("plugin-a", ["foo", "foo2"])
    assert registry.owner_of("foo2") == "plugin-a"


def test_unregister_is_idempotent_and_clears_ownership() -> None:
    registry = UnitRouteRegistry()
    registry.register("plugin-a", ["foo"])
    registry.subscribe_events("plugin-a", ["plugin_crashed"])
    registry.unregister("plugin-a")
    assert registry.owner_of("foo") is None
    assert registry.event_subscribers == {}
    # 幂等：再注销不炸
    registry.unregister("plugin-a")


def test_event_multi_subscriber_coexistence() -> None:
    registry = UnitRouteRegistry()
    registry.subscribe_events("unit-a", ["plugin_negotiated"])
    registry.subscribe_events("unit-b", ["plugin_negotiated"])
    subscribers = registry.event_subscribers["plugin_negotiated"]
    assert subscribers == {"unit-a", "unit-b"}


def test_builtin_registration_no_mutual_exclusion() -> None:
    """builtin/core 多实例同名共存合法（登记面如实、互斥面收窄）。"""
    registry = UnitRouteRegistry()
    registry.register_builtin("core_cluster", ["spawn_agent", "list_agents"])
    registry.register_builtin("core", ["spawn_agent", "send_message"])
    # 后登记者覆盖 owner 名（登记面如实记录最新），不 raise
    assert registry.owner_of("spawn_agent") == "core"
    # 插件路径撞 builtin 命令仍拒
    with pytest.raises(PluginMountError) as excinfo:
        registry.register("plugin-x", ["spawn_agent"])
    assert "already owned by unit 'core'" in str(excinfo.value)
