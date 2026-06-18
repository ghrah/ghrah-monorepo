from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ghrah.subject.runtime import service_keys
from ghrah.subject.runtime.service_keys import SubjectServiceKey


def test_subject_service_key_is_frozen_hashable_and_typed() -> None:
    key = SubjectServiceKey[str]("example", str)

    assert key.name == "example"
    assert key.service_type is str
    assert {key: "value"}[key] == "value"

    with pytest.raises(FrozenInstanceError):
        key.name = "changed"  # type: ignore[misc]


def test_global_service_key_names_are_unique() -> None:
    keys = [
        value
        for value in vars(service_keys).values()
        if isinstance(value, SubjectServiceKey)
    ]
    names = [key.name for key in keys]

    assert len(names) == len(set(names))
    assert "workspace_service" in names
    assert "capability_registry" in names
    assert "core_transport" in names
