# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for built-in Subject units."""

from __future__ import annotations

from typing import Any

__all__ = ["manifest_command_to_event", "manifest_result_to_event_payload"]


def manifest_command_to_event(command: str, payload: dict[str, Any]) -> str | None:
    """Map manifest CRUD commands to Observer/Core manifest event names."""

    overwrite = payload.get("overwrite", False)
    event_map: dict[str, str] = {
        "manifest_put_ability": (
            "manifest_ability_updated" if overwrite else "manifest_ability_created"
        ),
        "manifest_delete_ability": "manifest_ability_deleted",
        "manifest_put_agent": (
            "manifest_agent_updated" if overwrite else "manifest_agent_created"
        ),
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
