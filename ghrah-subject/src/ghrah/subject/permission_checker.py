"""Subject 端权限检查器。

基于 manifest PermissionFlags 进行权限判断。

权限模型：
- manifest 权限标志（fs_write, fs_read_only, shell_access, require_hitl）决定能力分类
- 路径权限：allowed_paths 白名单 + workspace_root 控制硬性允许/拒绝
- 命令权限：CommandSafetyChecker 分类 + denied_commands 黑名单
- Manifest 中声明的 denied_paths 直接拒绝
- 未在 manifest 中注册的能力走兜底逻辑（无路径安全关注 → ALLOW）

与 HITLPolicy 的职责划分：
- PermissionChecker：硬性权限（DENY / REQUIRE_HITL / ALLOW）
- HITLPolicy：审批策略（是否需要 HITL 审批）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from ghrah.abilities import (  # type: ignore[import-untyped]
    CommandSafetyCategory,
    CommandSafetyChecker,
)
from ghrah.abilities.paths import extract_paths, is_subpath  # type: ignore[import-untyped]
from ghrah.manifest.types import PermissionFlags  # type: ignore[import-untyped]

__all__ = ["PermissionChecker", "PermissionDecision", "PermissionVerdict"]


class _ManifestPermissionIndex(Protocol):
    def get_permissions(self) -> dict[str, PermissionFlags]:
        """Return the current manifest permission index."""


class PermissionDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HITL = "require_hitl"


@dataclass
class PermissionVerdict:
    decision: PermissionDecision
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class PermissionChecker:
    """Subject 端权限检查器。

    统一管理 allowed_paths 白名单和 workspace_root 工作路径，
    为 AbilityRunner 提供硬性权限检查（拒绝 vs 需要 HITL vs 允许）。

    能力分类从 manifest PermissionFlags 中获取：
    - fs_write=True → 写入路径检查
    - fs_read_only=True（且 fs_write=False）→ 读取路径检查
    - shell_access=True → 命令安全检查 + 工作目录权限
    - 均为 False → 无路径安全关注，返回 ALLOW
    - 未在 manifest 中注册 → 返回 ALLOW（由 HITLPolicy 决定是否需要审批）

    manifest 的 denied_paths 和 denied_commands 直接作为硬性拒绝规则。
    """

    def __init__(
        self,
        allowed_paths: list[str] | None = None,
        workspace_root: str | None = None,
        require_approval: bool = True,
        command_checker: CommandSafetyChecker | None = None,
        manifest_permissions: dict[str, PermissionFlags] | None = None,
        manifest_permission_index: _ManifestPermissionIndex | None = None,
    ) -> None:
        self._allowed_paths = self._normalize_paths(allowed_paths) if allowed_paths else None
        self._workspace_root = os.path.abspath(workspace_root) if workspace_root else None
        self._require_approval = require_approval
        self._command_checker = command_checker or CommandSafetyChecker()
        self._manifest_permissions: dict[str, PermissionFlags] = manifest_permissions or {}
        self._manifest_permission_index = manifest_permission_index

    @staticmethod
    def _normalize_paths(paths: list[str]) -> list[str]:
        return [os.path.abspath(p) for p in paths]

    def _is_in_allowed_paths(self, path: str) -> bool:
        if self._allowed_paths is None:
            return False
        abs_path = os.path.abspath(path)
        return any(bool(is_subpath(abs_path, allowed)) for allowed in self._allowed_paths)

    def _is_in_workspace(self, path: str) -> bool:
        if self._workspace_root is None:
            return False
        abs_path = os.path.abspath(path)
        return bool(is_subpath(abs_path, self._workspace_root))

    def _is_path_allowed(self, path: str) -> bool:
        return self._is_in_allowed_paths(path) or self._is_in_workspace(path)

    def check_read_path(self, path: str) -> tuple[bool, str]:
        """检查读取路径权限。"""
        abs_path = os.path.abspath(path)
        if self._allowed_paths is None and self._workspace_root is None:
            return True, ""
        if self._is_path_allowed(abs_path):
            return True, ""
        return False, f"Permission denied: {path} not in allowed paths"

    def check_write_path(self, path: str) -> tuple[bool, str | None]:
        """检查写入路径权限。"""
        abs_path = os.path.abspath(path)
        if self._allowed_paths is None and self._workspace_root is None:
            if self._require_approval:
                return True, "pending"
            return True, None
        if self._is_path_allowed(abs_path):
            return True, None
        if self._require_approval:
            return True, "pending"
        return False, f"Permission denied: {path} not in allowed paths"

    def check_ability(
        self,
        ability_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> PermissionVerdict:
        """综合检查 Ability 操作权限。

        基于 manifest PermissionFlags 决定能力分类：
        - shell_access=True → 命令安全检查
        - fs_write=True → 写入路径检查
        - fs_read_only=True（且非 fs_write）→ 读取路径检查
        - 均为 False 或未注册 → 无路径安全关注，返回 ALLOW

        manifest 的 denied_paths 在路径检查前优先判断（硬性拒绝）。
        manifest 的 denied_commands 在命令检查前优先判断（硬性拒绝）。
        """
        manifest_perms = self._get_manifest_permissions().get(ability_name)

        # 未在 manifest 中注册的能力：无路径安全关注
        if manifest_perms is None:
            return PermissionVerdict(
                decision=PermissionDecision.ALLOW,
                reason="no_path_security_concern",
            )

        # 命令类能力
        if manifest_perms.shell_access and tool_args:
            return self._check_command(ability_name, tool_args, manifest_perms)

        # 写入类能力（fs_write 隐含 fs_read_only 的含义，因为 move 也读）
        if manifest_perms.fs_write and tool_args:
            paths = extract_paths(ability_name, tool_args)
            # 写入路径检查
            write_paths = paths
            if manifest_perms.fs_read_only and ability_name == "move_file":
                src = tool_args.get("source_path") or tool_args.get("file_path")
                dst = tool_args.get("destination_path")
                write_paths = [dst] if dst else []
                read_paths = [src] if src else []
                for rp in read_paths:
                    if manifest_perms.denied_paths and self._path_in_deny_list(
                        rp,
                        manifest_perms.denied_paths,
                    ):
                        return PermissionVerdict(
                            decision=PermissionDecision.DENY,
                            reason=f"Path denied by manifest: {rp}",
                            metadata={"path": rp, "ability_name": ability_name},
                        )
                    allowed, reason = self.check_read_path(rp)
                    if not allowed:
                        return PermissionVerdict(
                            decision=PermissionDecision.DENY,
                            reason=reason,
                            metadata={"path": rp, "ability_name": ability_name},
                        )
            return self._check_write_paths_with_deny(ability_name, write_paths, manifest_perms)

        # 只读类能力
        if manifest_perms.fs_read_only and tool_args:
            paths = extract_paths(ability_name, tool_args)
            return self._check_read_paths_with_deny(ability_name, paths, manifest_perms)

        # 其他能力（如 conversation, end_task）：无路径安全关注
        return PermissionVerdict(
            decision=PermissionDecision.ALLOW,
            reason="no_path_security_concern",
        )

    def _path_in_deny_list(self, path: str, denied_paths: list[str]) -> bool:
        """检查路径是否在 manifest denied_paths 中。"""
        abs_path = os.path.abspath(path)
        for denied in denied_paths:
            if is_subpath(abs_path, os.path.abspath(denied)):
                return True
        return False

    def _check_write_paths_with_deny(
        self, ability_name: str, paths: list[str], manifest_perms: PermissionFlags
    ) -> PermissionVerdict:
        for path in paths:
            if manifest_perms.denied_paths and self._path_in_deny_list(
                path,
                manifest_perms.denied_paths,
            ):
                return PermissionVerdict(
                    decision=PermissionDecision.DENY,
                    reason=f"Path denied by manifest: {path}",
                    metadata={"path": path, "ability_name": ability_name},
                )
            allowed, status = self.check_write_path(path)
            if not allowed:
                return PermissionVerdict(
                    decision=PermissionDecision.DENY,
                    reason=status or f"Permission denied: {path}",
                    metadata={"path": path, "ability_name": ability_name},
                )
            if status == "pending":
                return PermissionVerdict(
                    decision=PermissionDecision.REQUIRE_HITL,
                    reason=f"Write operation requires HITL approval: {path}",
                    metadata={"path": path, "ability_name": ability_name},
                )
        return PermissionVerdict(
            decision=PermissionDecision.ALLOW,
            reason="path_in_allowed_scope",
            metadata={"paths": paths, "ability_name": ability_name},
        )

    def _check_read_paths_with_deny(
        self, ability_name: str, paths: list[str], manifest_perms: PermissionFlags
    ) -> PermissionVerdict:
        for path in paths:
            if manifest_perms.denied_paths and self._path_in_deny_list(
                path,
                manifest_perms.denied_paths,
            ):
                return PermissionVerdict(
                    decision=PermissionDecision.DENY,
                    reason=f"Path denied by manifest: {path}",
                    metadata={"path": path, "ability_name": ability_name},
                )
            allowed, reason = self.check_read_path(path)
            if not allowed:
                return PermissionVerdict(
                    decision=PermissionDecision.DENY,
                    reason=reason,
                    metadata={"path": path, "ability_name": ability_name},
                )
        return PermissionVerdict(
            decision=PermissionDecision.ALLOW,
            reason="path_in_allowed_scope",
            metadata={"paths": paths, "ability_name": ability_name},
        )

    def _check_command(
        self,
        ability_name: str,
        tool_args: dict[str, Any],
        manifest_perms: PermissionFlags,
    ) -> PermissionVerdict:
        """检查命令类 Ability 权限。"""
        command = tool_args.get("command", "")
        if not command:
            return PermissionVerdict(
                decision=PermissionDecision.DENY,
                reason="Empty command",
                metadata={"ability_name": ability_name},
            )

        # manifest denied_commands 优先判断
        if manifest_perms.denied_commands:
            for denied_cmd in manifest_perms.denied_commands:
                command_text = command.strip()
                denied_text = denied_cmd.strip()
                if command_text == denied_text or command_text.startswith(
                    denied_text + " "
                ):
                    return PermissionVerdict(
                        decision=PermissionDecision.DENY,
                        reason=f"Command denied by manifest: {denied_cmd}",
                        metadata={"command": command, "ability_name": ability_name},
                    )

        working_dir = tool_args.get("working_dir")
        if working_dir:
            abs_wd = os.path.abspath(working_dir)
            if self._allowed_paths is not None or self._workspace_root is not None:
                if not self._is_path_allowed(abs_wd):
                    return PermissionVerdict(
                        decision=PermissionDecision.DENY,
                        reason=f"Working directory not allowed: {working_dir}",
                        metadata={"path": working_dir, "ability_name": ability_name},
                    )

        verdict = self._command_checker.check_command(command)
        if verdict.category == CommandSafetyCategory.SAFE:
            return PermissionVerdict(
                decision=PermissionDecision.ALLOW,
                reason="command_safe",
                metadata={"command": command, "ability_name": ability_name},
            )
        if verdict.category == CommandSafetyCategory.DANGEROUS:
            return PermissionVerdict(
                decision=PermissionDecision.DENY,
                reason=verdict.reason,
                metadata={"command": command, "ability_name": ability_name},
            )
        else:
            return PermissionVerdict(
                decision=PermissionDecision.REQUIRE_HITL,
                reason=verdict.reason,
                metadata={"command": command, "ability_name": ability_name},
            )

    def _get_manifest_permissions(self) -> dict[str, PermissionFlags]:
        if self._manifest_permission_index is not None:
            return self._manifest_permission_index.get_permissions()
        return self._manifest_permissions

    @property
    def allowed_paths(self) -> list[str] | None:
        return self._allowed_paths

    @property
    def workspace_root(self) -> str | None:
        return self._workspace_root
