# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Typed service registry for Subject runtime units."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from ghrah.subject.runtime.service_keys import SubjectServiceKey

__all__ = ["SubjectServices"]

T = TypeVar("T")


class SubjectServices:
    """Mutable registry for services shared between Subject units."""

    def __init__(
        self,
        initial: Mapping[SubjectServiceKey[Any], Any] | None = None,
    ) -> None:
        self._services: dict[str, Any] = {}
        if initial is not None:
            for key, value in initial.items():
                self.set(key, value)

    def get(self, key: SubjectServiceKey[T], default: T | None = None) -> T | None:
        """Return a service by key, or default if it has not been set."""

        return cast(T | None, self._services.get(key.name, default))

    def require(self, key: SubjectServiceKey[T]) -> T:
        """Return a required service or raise a clear error."""

        if key.name not in self._services or self._services[key.name] is None:
            raise RuntimeError(f"Required subject service '{key.name}' is not set.")
        return cast(T, self._services[key.name])

    def set(self, key: SubjectServiceKey[T], value: T) -> None:
        """Set a service by typed key."""

        self._services[key.name] = value

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow snapshot of registered services."""

        return dict(self._services)
