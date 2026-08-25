# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for built-in Subject units."""

from __future__ import annotations

from typing import Any

from ghrah.abilities import (  # type: ignore[import-untyped]
    FS_ABILITY_TYPES,
    resolve_fs_permission_paths,
)
from ghrah.manifest.types import PermissionFlags  # type: ignore[import-untyped]

__all__ = [
    "manifest_command_to_event",
    "manifest_result_to_event_payload",
    "materialize_permission_params",
]


def manifest_command_to_event(command: str, payload: dict[str, Any]) -> str | None:
    """Map manifest CRUD commands to Observer/Core manifest event names."""

    overwrite = payload.get("overwrite", False)
    event_map: dict[str, str] = {
        "manifest_put_ability": (
            "manifest_ability_updated" if overwrite else "manifest_ability_created"
        ),
        "manifest_delete_ability": "manifest_ability_deleted",
        "manifest_put_agent": ("manifest_agent_updated" if overwrite else "manifest_agent_created"),
        "manifest_delete_agent": "manifest_agent_deleted",
    }
    return event_map.get(command)


def manifest_result_to_event_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Build the wire event payload emitted after successful manifest CRUD."""

    data = result.get("data", {})
    full_name = data.get("full_name", "")
    namespace = full_name.rsplit(".", 1)[0] if "." in full_name else ""
    event_payload: dict[str, Any] = {
        "full_name": full_name,
        "namespace": namespace,
    }
    if "manifest" in data:
        event_payload["manifest"] = data["manifest"]
    if "source" in data:
        event_payload["source"] = data["source"]
    return event_payload


def materialize_permission_params(
    ability_type: str,
    permissions: PermissionFlags,
    workspace_root: str | None,
) -> dict[str, Any]:
    """Build Core ability-constructor params from resolved manifest permissions.

    Core consumes these fields in ``MessageRouter._create_ability_from_def``.
    Keep the output limited to ability types whose constructors/router adapters
    understand the fields; arbitrary builtins must not receive permission-only
    kwargs such as ``require_hitl``.
    """

    params: dict[str, Any] = {}
    has_fs_permissions = (
        ability_type in FS_ABILITY_TYPES
        or permissions.fs_read_only
        or permissions.fs_write
        or bool(permissions.allowed_paths)
        or bool(permissions.denied_paths)
    )

    if has_fs_permissions:
        params["require_hitl"] = permissions.require_hitl
        allowed_paths = permissions.allowed_paths or None
        denied_paths = permissions.denied_paths or None
        if workspace_root:
            allowed_paths, denied_paths = resolve_fs_permission_paths(
                allowed_paths,
                denied_paths,
                {"workspace": workspace_root},
                workspace_root,
            )
            params["workspace_root"] = workspace_root
        if allowed_paths:
            params["allowed_paths"] = allowed_paths
        if denied_paths:
            params["denied_paths"] = denied_paths

    if ability_type == "execute_command" or permissions.shell_access:
        params["require_approval"] = permissions.require_hitl

    return params
