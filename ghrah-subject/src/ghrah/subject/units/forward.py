# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Forward built-in Subject unit.

Routes Core-domain commands through the configured ``CORE_TRANSPORT``. For
``spawn_agent`` manifest spawns it materializes resolved manifest permissions
into Core ability params, fixing the old ``params={}`` loss.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from ghrah.manifest.resolver import ManifestResolver  # type: ignore[import-untyped]
from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.service_keys import (
    CAPABILITY_REGISTRY,
    CORE_TRANSPORT,
    MANIFEST_STORE,
    WORKSPACE_SERVICE,
)
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta
from ghrah.subject.units._commands import CORE_COMMANDS
from ghrah.subject.units._helpers import materialize_permission_params

__all__ = ["ForwardUnit"]

logger = logging.getLogger(__name__)

_FORWARD_TIMEOUT = 30.0


class ForwardUnit(SubjectUnit):
    """Forwards Core command set messages through the active Core transport."""

    def __init__(self, config: SubjectConfig) -> None:
        self._config = config
        self._ctx: SubjectContext | None = None
        self._meta = UnitMeta(
            name="forward",
            requires=frozenset({
                MANIFEST_STORE,
                CAPABILITY_REGISTRY,
                CORE_TRANSPORT,
                WORKSPACE_SERVICE,
            }),
            # D10: CORE_COMMANDS live only in long_running_commands here.
            routes=RouteSpec(long_running_commands=CORE_COMMANDS),
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def init(self, ctx: SubjectContext) -> None:
        self._ctx = ctx

    async def handle_command(
        self,
        command: str,
        payload: dict[str, Any],
        cmd_ctx: CommandContext,
    ) -> dict[str, Any]:
        if command not in CORE_COMMANDS:
            return {"success": False, "error": f"Unknown forward command: {command}"}

        ctx = self._require_context()
        outgoing_payload = dict(payload)
        if command == "spawn_agent" and outgoing_payload.get("manifest_ref"):
            outgoing_payload = self._resolve_spawn_manifest(outgoing_payload)

        message: dict[str, Any] = {
            "type": command,
            "payload": outgoing_payload,
            "client_type": "subject",
        }
        if cmd_ctx.request_id is not None:
            message["request_id"] = cmd_ctx.request_id

        transport = ctx.services.require(CORE_TRANSPORT)
        return await transport.send_and_wait(message, timeout=_FORWARD_TIMEOUT)

    def _resolve_spawn_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Expand ``manifest_ref`` into the concrete Core ``spawn_agent`` payload."""

        ctx = self._require_context()
        manifest_ref = str(payload["manifest_ref"])
        config_payload = payload.get("config", {})
        runtime_name = (
            config_payload.get("name")
            if isinstance(config_payload, dict)
            else None
        )

        store = ctx.services.require(MANIFEST_STORE)
        manifest = store.get_agent(manifest_ref)
        resolved = ManifestResolver(store).resolve(manifest, runtime_name=runtime_name)
        workspace_root = self._spawn_workspace_root(resolved.config.name)

        expanded_abilities: list[dict[str, Any]] = []
        for ability in resolved.abilities:
            implementation = ability.implementation
            if implementation.type == "builtin" and implementation.handler:
                expanded_abilities.append({
                    "ability_type": implementation.handler,
                    "params": materialize_permission_params(
                        implementation.handler,
                        ability.permissions,
                        workspace_root,
                    ),
                })
                continue
            logger.warning(
                "Skipping non-builtin ability '%s' (type=%s) in manifest spawn",
                ability.ability_name,
                implementation.type,
            )

        return {
            "config": _agent_config_to_payload(resolved.config),
            "abilities": expanded_abilities if expanded_abilities else None,
            "manifest_ref": None,
        }

    def _spawn_workspace_root(self, agent_name: str) -> str | None:
        """Return workspace path via the typed workspace service only."""

        workspace = self._require_context().services.require(WORKSPACE_SERVICE)
        return workspace.resolve_agent_path(agent_name)

    def _require_context(self) -> SubjectContext:
        if self._ctx is None:
            raise RuntimeError("ForwardUnit has not been initialized.")
        return self._ctx


def _agent_config_to_payload(config: Any) -> dict[str, Any]:
    return {
        "name": config.name,
        "agent_config_name": config.agent_config_name,
        "description": config.description,
        "system_prompt": config.system_prompt,
        "max_iterations": config.max_iterations,
        "communication_timeout": config.communication_timeout,
        "window": dataclasses.asdict(config.window) if config.window else None,
        "context": dataclasses.asdict(config.context) if config.context else None,
        "model_overrides": (
            dataclasses.asdict(config.model_overrides)
            if config.model_overrides
            else None
        ),
    }
