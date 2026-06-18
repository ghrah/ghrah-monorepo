from __future__ import annotations

import pytest

from ghrah.subject.runtime.service_keys import SubjectServiceKey
from ghrah.subject.runtime.services import SubjectServices


def test_set_get_require_and_snapshot() -> None:
    key = SubjectServiceKey[dict[str, int]]("numbers")
    services = SubjectServices()
    value = {"one": 1}

    services.set(key, value)

    assert services.get(key) is value
    assert services.require(key) is value

    snapshot = services.snapshot()
    snapshot["numbers"] = {"two": 2}
    assert services.require(key) is value


def test_get_default_and_require_missing() -> None:
    key = SubjectServiceKey[str]("missing")
    services = SubjectServices()

    assert services.get(key, "fallback") == "fallback"
    with pytest.raises(RuntimeError, match="Required subject service 'missing' is not set"):
        services.require(key)
