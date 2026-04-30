from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ghrah.manifest.types import PermissionFlags
from ghrah.subject._utils import is_subpath

__all__ = ["HITLVerdict", "HITLPolicy"]


@dataclass
class HITLVerdict:
    approved: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class HITLPolicy:
    """HITL 审批策略：决定能力执行是否需要人工审批。

    权限决策的真相源是 manifest 的 PermissionFlags：
    - require_hitl=False → 无需 HITL 审批（如 conversation、end_task）
    - require_hitl=True → 需要 HITL 审批或路径检查通过后放行

    运行时覆盖层：
    - auto_approve_abilities：管理员可强制放行任何能力（包括 manifest 标记 require_hitl=True 的能力）
    - require_approval_by_default：对未在 manifest 中注册的能力的兜底策略

    决策流程（按优先级）：
    1. auto_approve_abilities 白名单 → 直接放行
    2. manifest permissions 查询：
       - require_hitl=False → 放行（manifest_auto_approved）
       - require_hitl=True → 继续路径检查
    3. 未找到 manifest permissions → 按 require_approval_by_default 决定
    4. 有 tool_args 时做路径检查（现有逻辑不变）
    """

    def __init__(
        self,
        auto_approve_abilities: list[str] | None = None,
        require_approval_by_default: bool = True,
        allowed_paths: list[str] | None = None,
        workspace_root: str | None = None,
        manifest_permissions: dict[str, PermissionFlags] | None = None,
    ) -> None:
        self._auto_approve_abilities: set[str] = set(auto_approve_abilities or [])
        self._require_approval_by_default = require_approval_by_default
        self._allowed_paths = self._normalize_paths(allowed_paths) if allowed_paths else None
        self._workspace_root = os.path.abspath(workspace_root) if workspace_root else None
        self._manifest_permissions: dict[str, PermissionFlags] = manifest_permissions or {}

    @staticmethod
    def _normalize_paths(paths: list[str]) -> list[str]:
        return [os.path.abspath(p) for p in paths]

    def _is_in_allowed_paths(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        if self._allowed_paths is None:
            return False
        return any(is_subpath(abs_path, allowed) for allowed in self._allowed_paths)

    def _is_in_workspace(self, path: str) -> bool:
        if self._workspace_root is None:
            return False
        abs_path = os.path.abspath(path)
        return is_subpath(abs_path, self._workspace_root)

    def _is_path_allowed(self, path: str) -> bool:
        return self._is_in_allowed_paths(path) or self._is_in_workspace(path)

    def check_ability(
        self,
        ability_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> HITLVerdict:
        # 1. 运行时覆盖：管理员强制放行
        if ability_name in self._auto_approve_abilities:
            return HITLVerdict(approved=True, reason="auto_approved")

        # 2. Manifest 权限声明：require_hitl 标记
        manifest_perms = self._manifest_permissions.get(ability_name)
        if manifest_perms is not None:
            if not manifest_perms.require_hitl:
                return HITLVerdict(approved=True, reason="manifest_auto_approved")
            # require_hitl=True → 继续到路径检查

        # 3. 路径检查（对 require_hitl=True 和未知能力均适用）
        if tool_args:
            paths = self._extract_paths(ability_name, tool_args)
            if paths:
                return self._check_paths(ability_name, paths)

        # 4. 无可检查路径时的兜底策略
        if manifest_perms is None:
            if self._require_approval_by_default:
                return HITLVerdict(approved=False, reason="requires_hitl_approval")
            return HITLVerdict(approved=True, reason="auto_approved_by_default")

        # 5. require_hitl=True 且无可检查路径 → 需要 HITL 审批
        return HITLVerdict(approved=False, reason="requires_hitl_approval")

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
            src = tool_args.get("source_path") or tool_args.get("file_path")
            dst = tool_args.get("destination_path")
            if src:
                paths.append(src)
            if dst:
                paths.append(dst)
        else:
            path = tool_args.get("file_path") or tool_args.get("dir_path") or tool_args.get("working_dir")
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

    @property
    def manifest_permissions(self) -> dict[str, PermissionFlags]:
        return self._manifest_permissions
