from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

__all__ = ["HITLVerdict", "HITLPolicy"]


def _is_subpath(path: str, parent: str) -> bool:
    path_abs = os.path.abspath(path)
    parent_abs = os.path.abspath(parent)
    if parent_abs == path_abs:
        return True
    return path_abs.startswith(parent_abs + os.sep)


@dataclass
class HITLVerdict:
    approved: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class HITLPolicy:
    def __init__(
        self,
        auto_approve_abilities: list[str] | None = None,
        require_approval_by_default: bool = True,
        allowed_paths: list[str] | None = None,
        workspace_root: str | None = None,
    ) -> None:
        self._auto_approve_abilities: set[str] = set(auto_approve_abilities or [])
        self._require_approval_by_default = require_approval_by_default
        self._allowed_paths = self._normalize_paths(allowed_paths) if allowed_paths else None
        self._workspace_root = os.path.abspath(workspace_root) if workspace_root else None

    @staticmethod
    def _normalize_paths(paths: list[str]) -> list[str]:
        return [os.path.abspath(p) for p in paths]

    def _is_in_allowed_paths(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        if self._allowed_paths is None:
            return False
        return any(_is_subpath(abs_path, allowed) for allowed in self._allowed_paths)

    def _is_in_workspace(self, path: str) -> bool:
        if self._workspace_root is None:
            return False
        abs_path = os.path.abspath(path)
        return _is_subpath(abs_path, self._workspace_root)

    def _is_path_allowed(self, path: str) -> bool:
        return self._is_in_allowed_paths(path) or self._is_in_workspace(path)

    def check_ability(
        self,
        ability_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> HITLVerdict:
        if ability_name in self._auto_approve_abilities:
            return HITLVerdict(approved=True, reason="auto_approved")

        if tool_args:
            paths = self._extract_paths(ability_name, tool_args)
            if paths:
                return self._check_paths(ability_name, paths)

        if self._require_approval_by_default:
            return HITLVerdict(approved=False, reason="requires_hitl_approval")

        return HITLVerdict(approved=True, reason="auto_approved_by_default")

    def _check_paths(self, ability_name: str, paths: list[str]) -> HITLVerdict:
        for path in paths:
            if not self._is_path_allowed(path):
                if self._require_approval_by_default:
                    return HITLVerdict(
                        approved=False,
                        reason="path_requires_hitl_approval",
                        metadata={"path": path},
                    )
                return HITLVerdict(
                    approved=True,
                    reason="path_auto_approved_by_default",
                    metadata={"path": path},
                )
        return HITLVerdict(
            approved=True,
            reason="path_in_allowed_scope",
            metadata={"paths": paths},
        )

    @staticmethod
    def _extract_paths(
        ability_name: str, tool_args: dict[str, Any]
    ) -> list[str]:
        paths: list[str] = []
        if ability_name == "move_file":
            src = tool_args.get("file_path")
            dst = tool_args.get("destination_path")
            if src:
                paths.append(src)
            if dst:
                paths.append(dst)
        else:
            path = tool_args.get("file_path")
            if path:
                paths.append(path)
        return paths

    @property
    def auto_approve_abilities(self) -> set[str]:
        return self._auto_approve_abilities

    @property
    def allowed_paths(self) -> list[str] | None:
        return self._allowed_paths

    @property
    def workspace_root(self) -> str | None:
        return self._workspace_root
