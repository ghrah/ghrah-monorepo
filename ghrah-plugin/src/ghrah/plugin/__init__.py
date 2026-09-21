# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""插件基础设施。

零 ghrah 域包依赖：本包与 pydantic/packaging 同级，是插件契约（plugin spec）
的唯一权威（SSOT）。发现 ≠ 启用；挂载与信任闸强制执行归 ghrah-subject。
"""

from ghrah.plugin.assembly import PluginAssembly, PluginInstanceConfig, validate_assembly
from ghrah.plugin.errors import CapabilityMissingError, PluginMountError
from ghrah.plugin.loader import DiscoveredPlugin, LoadIssue, discover_plugins
from ghrah.plugin.negotiator import (
    NegotiationResult,
    PythonHalfInfo,
    TsHalfReport,
    negotiate,
)
from ghrah.plugin.registry import PluginRegistry
from ghrah.plugin.spec import PluginSpec, migrate_spec, plugin_spec_json_schema
from ghrah.plugin.verify import Finding, verify_plugins

__all__ = [
    "CapabilityMissingError",
    "DiscoveredPlugin",
    "Finding",
    "LoadIssue",
    "NegotiationResult",
    "PluginAssembly",
    "PluginInstanceConfig",
    "PluginMountError",
    "PluginRegistry",
    "PluginSpec",
    "PythonHalfInfo",
    "TsHalfReport",
    "discover_plugins",
    "migrate_spec",
    "negotiate",
    "plugin_spec_json_schema",
    "validate_assembly",
    "verify_plugins",
]
