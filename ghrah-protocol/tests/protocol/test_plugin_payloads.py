# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""plugin_negotiate 与 plugin_* 事件 wire 契约测试。"""

from __future__ import annotations

from ghrah.plugin.negotiator import (
    NegotiationResult,
    PythonHalfInfo,
    TsHalfReport,
    negotiate,
)

from ghrah.protocol.types import (
    PluginCrashedPayload,
    PluginLifecyclePayload,
    PluginNegotiatedPayload,
    PluginNegotiatePayload,
    PluginNegotiateResultPayload,
)


class TestNegotiateWire:
    def test_request_payload_carries_ts_half_reports(self) -> None:
        payload = PluginNegotiatePayload(
            enabled_ts=[
                {
                    "plugin_id": "task-commit-attribution",
                    "version": "1.0.0",
                    "provides": ["badge/git_commit"],
                },
                TsHalfReport(plugin_id="demo", version="0.2.0", provides=["checker/x"]),
            ]
        )
        assert payload.enabled_ts[0].plugin_id == "task-commit-attribution"
        assert payload.enabled_ts[1].provides == ["checker/x"]
        wire = payload.model_dump(mode="json")
        assert wire["enabled_ts"][0]["version"] == "1.0.0"

    def test_request_payload_defaults_to_empty(self) -> None:
        assert PluginNegotiatePayload().enabled_ts == []

    def test_result_payload_shape_equals_negotiator_output(self) -> None:
        """子类零漂移探针：wire 结果形状 = negotiator 纯函数输出，单一权威。"""
        result = negotiate(
            [
                PythonHalfInfo(
                    plugin_id="demo",
                    version="1.0.0",
                    provides=["checker/x"],
                    requires_capabilities=["core:z"],
                )
            ],
            [TsHalfReport(plugin_id="demo", version="1.0.0", provides=["badge/y"])],
        )
        wire = PluginNegotiateResultPayload.model_validate(result.model_dump(mode="json"))
        assert wire.model_dump(mode="json") == result.model_dump(mode="json")
        assert wire.matched[0].provides == ["checker/x", "badge/y"]

    def test_result_payload_reuses_negotiation_result_class(self) -> None:
        """PluginNegotiateResultPayload 是 NegotiationResult 的子类（零字段重复）。"""
        assert issubclass(PluginNegotiateResultPayload, NegotiationResult)


class TestPluginEvents:
    def test_lifecycle_payload_fields(self) -> None:
        payload = PluginLifecyclePayload(
            plugin_id="task-commit-attribution",
            version="1.0.0",
            instance_ids=["prod-eu", "staging"],
        )
        wire = payload.model_dump(mode="json")
        assert wire == {
            "plugin_id": "task-commit-attribution",
            "version": "1.0.0",
            "instance_ids": ["prod-eu", "staging"],
        }

    def test_negotiated_payload_is_pure_signal(self) -> None:
        payload = PluginNegotiatedPayload(changed=["demo-plugin"])
        assert payload.model_dump(mode="json") == {"changed": ["demo-plugin"]}
        assert PluginNegotiatedPayload().changed == []

    def test_crashed_payload_carries_command_and_error(self) -> None:
        """崩溃可见性契约：插件 id / 命令名 / 异常摘要三要素在 wire 上齐全。"""
        payload = PluginCrashedPayload(
            plugin_id="demo-plugin",
            command="command/demo_run",
            error="ValueError: boom",
            instance_id="prod-eu",
        )
        wire = payload.model_dump(mode="json")
        assert wire["plugin_id"] == "demo-plugin"
        assert wire["command"] == "command/demo_run"
        assert wire["error"] == "ValueError: boom"
        assert wire["instance_id"] == "prod-eu"

    def test_crashed_payload_instance_optional(self) -> None:
        payload = PluginCrashedPayload(plugin_id="p", command="c", error="e")
        assert payload.instance_id is None
