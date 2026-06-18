# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Capability provider contracts for future Subject plugin units."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ghrah.manifest.types import PermissionFlags  # type: ignore[import-untyped]

__all__ = [
    "AbilityContribution",
    "CapabilityProvider",
    "CapabilityRegistry",
    "PermissionDescriptor",
]


@dataclass(frozen=True)
class AbilityContribution:
    """Ability contributed by a Subject unit."""

    namespace: str
    name: str
    tool_schema: dict[str, Any]
    permissions: PermissionFlags
    implementation_handler: Any

    @property
    def full_name(self) -> str:
        """Return the stable ``namespace.name`` ability key."""

        return f"{self.namespace}.{self.name}"


@dataclass(frozen=True)
class PermissionDescriptor:
    """Namespace-level permission rules contributed by a Subject unit."""

    namespace: str
    rules: PermissionFlags


class CapabilityProvider(Protocol):
    """Protocol implemented by units that contribute abilities."""

    def list_abilities(self) -> list[AbilityContribution]:
        """Return abilities contributed by this provider."""

    def describe_permissions(self) -> list[PermissionDescriptor]:
        """Return namespace-level permission descriptors."""


class CapabilityRegistry:
    """Registry of ability and permission contributions from Subject units."""

    def __init__(self) -> None:
        self._providers: dict[str, CapabilityProvider] = {}

    def register(self, unit_name: str, provider: CapabilityProvider) -> None:
        """Register a capability provider for a unit."""

        if unit_name in self._providers:
            raise ValueError(f"Capability provider already registered for unit '{unit_name}'.")

        existing = self._ability_names()
        for ability in provider.list_abilities():
            if ability.full_name in existing:
                raise ValueError(f"Ability '{ability.full_name}' is already registered.")
            existing.add(ability.full_name)

        self._providers[unit_name] = provider

    def all_abilities(self) -> list[AbilityContribution]:
        """Return all contributed abilities, validating uniqueness."""

        seen: set[str] = set()
        abilities: list[AbilityContribution] = []
        for provider in self._providers.values():
            for ability in provider.list_abilities():
                if ability.full_name in seen:
                    raise ValueError(f"Ability '{ability.full_name}' is already registered.")
                seen.add(ability.full_name)
                abilities.append(ability)
        return abilities

    def permission_index(self) -> dict[str, PermissionFlags]:
        """Build a merged ability permission index."""

        namespace_rules: dict[str, PermissionFlags] = {}
        for provider in self._providers.values():
            for descriptor in provider.describe_permissions():
                current = namespace_rules.get(descriptor.namespace)
                namespace_rules[descriptor.namespace] = (
                    descriptor.rules if current is None else current.merge(descriptor.rules)
                )

        index: dict[str, PermissionFlags] = {}
        for ability in self.all_abilities():
            base = namespace_rules.get(ability.namespace, PermissionFlags())
            index[ability.full_name] = base.merge(ability.permissions)
        return index

    def _ability_names(self) -> set[str]:
        return {ability.full_name for ability in self.all_abilities()}
