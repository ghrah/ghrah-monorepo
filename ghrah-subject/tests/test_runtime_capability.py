from __future__ import annotations

from dataclasses import dataclass

import pytest
from ghrah.manifest.types import PermissionFlags  # type: ignore[import-untyped]

from ghrah.subject.runtime.capability import (
    AbilityContribution,
    CapabilityRegistry,
    PermissionDescriptor,
)


@dataclass
class _Provider:
    abilities: list[AbilityContribution]
    permissions: list[PermissionDescriptor]

    def list_abilities(self) -> list[AbilityContribution]:
        return self.abilities

    def describe_permissions(self) -> list[PermissionDescriptor]:
        return self.permissions


def _ability(namespace: str, name: str, permissions: PermissionFlags) -> AbilityContribution:
    return AbilityContribution(
        namespace=namespace,
        name=name,
        tool_schema={"name": name},
        permissions=permissions,
        implementation_handler=object(),
    )


def test_registry_collects_abilities_and_merges_permission_index() -> None:
    registry = CapabilityRegistry()
    provider = _Provider(
        abilities=[
            _ability(
                "demo",
                "write",
                PermissionFlags(fs_write=True, denied_paths=["/tmp/blocked"]),
            )
        ],
        permissions=[
            PermissionDescriptor(
                namespace="demo",
                rules=PermissionFlags(shell_access=True, denied_paths=["/secret"]),
            )
        ],
    )

    registry.register("demo_unit", provider)

    abilities = registry.all_abilities()
    index = registry.permission_index()

    assert [ability.full_name for ability in abilities] == ["demo.write"]
    assert index["demo.write"].shell_access is True
    assert index["demo.write"].fs_write is True
    assert index["demo.write"].denied_paths == ["/secret", "/tmp/blocked"]


def test_duplicate_ability_registration_raises() -> None:
    registry = CapabilityRegistry()
    first = _Provider(
        abilities=[_ability("demo", "tool", PermissionFlags())],
        permissions=[],
    )
    second = _Provider(
        abilities=[_ability("demo", "tool", PermissionFlags())],
        permissions=[],
    )

    registry.register("one", first)
    with pytest.raises(ValueError, match="demo.tool"):
        registry.register("two", second)


def test_duplicate_unit_provider_raises() -> None:
    registry = CapabilityRegistry()
    provider = _Provider(abilities=[], permissions=[])

    registry.register("unit", provider)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("unit", provider)
