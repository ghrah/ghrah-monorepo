"""Project lifecycle boundary errors shared by scoped stores and managers."""

from __future__ import annotations


class ProjectArchivedError(Exception):
    """A project-scoped store was accessed while its Project Root is frozen."""
