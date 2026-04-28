"""Subject 端权限检查器。

迁移自 Core 的 FSPermissionChecker，适配 Subject 端执行环境。
与 Core 版本的关键区别：
- 增加 PermissionDecision 枚举，明确区分 ALLOW / DENY / REQUIRE_HITL
- 提供 check_ability() 综合方法，用于 AbilityRunner 集成
- 路径匹配使用 is_subpath 严格匹配（与 HITLPolicy 保持一致）
- 支持 execute_command 命令安全检查（委托 Core 的 CommandSafetyChecker）

权限模型：
- 读取操作：allowed_paths 白名单 + workspace_root 控制硬性允许/拒绝
- 写入操作：白名单内自动批准，白名单外需要 HITL 审批或拒绝
- 命令操作：CommandSafetyChecker 分类 + 工作目录路径权限
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from ghrah.abilities.builtin.command_safety import (
    CommandSafetyCategory,
    CommandSafetyChecker,
)
from ghrah.subject._utils import is_subpath

if TYPE_CHECKING:
    pass

__all__ = ["PermissionChecker", "PermissionDecision", "PermissionVerdict"]


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

    支持：
    - 文件系统 Ability：路径权限（读取/写入）
    - 命令执行 Ability：命令安全分类 + 工作目录路径权限
    """

    WRITE_ABILITIES = {"write_file", "edit_file", "move_file", "delete_file"}
    READ_ABILITIES = {"read_file", "list_directory"}
    COMMAND_ABILITIES = {"execute_command"}

    def __init__(
        self,
        allowed_paths: list[str] | None = None,
        workspace_root: str | None = None,
        require_approval: bool = True,
        command_checker: CommandSafetyChecker | None = None,
    ) -> None:
        self._allowed_paths = self._normalize_paths(allowed_paths) if allowed_paths else None
        self._workspace_root = os.path.abspath(workspace_root) if workspace_root else None
        self._require_approval = require_approval
        self._command_checker = command_checker or CommandSafetyChecker()

    @staticmethod
    def _normalize_paths(paths: list[str]) -> list[str]:
        return [os.path.abspath(p) for p in paths]

    def _is_in_allowed_paths(self, path: str) -> bool:
        if self._allowed_paths is None:
            return False
        abs_path = os.path.abspath(path)
        return any(is_subpath(abs_path, allowed) for allowed in self._allowed_paths)

    def _is_in_workspace(self, path: str) -> bool:
        if self._workspace_root is None:
            return False
        abs_path = os.path.abspath(path)
        return is_subpath(abs_path, self._workspace_root)

    def _is_path_allowed(self, path: str) -> bool:
        return self._is_in_allowed_paths(path) or self._is_in_workspace(path)

    def check_read_path(self, path: str) -> tuple[bool, str]:
        """检查读取路径权限。

        Returns:
            (True, ""): 允许访问
            (False, reason): 拒绝访问
        """
        abs_path = os.path.abspath(path)
        if self._allowed_paths is None and self._workspace_root is None:
            return True, ""
        if self._is_path_allowed(abs_path):
            return True, ""
        return False, f"Permission denied: {path} not in allowed paths"

    def check_write_path(self, path: str) -> tuple[bool, str | None]:
        """检查写入路径权限。

        Returns:
            (True, None): 自动批准
            (True, "pending"): 需要 HITL 审批
            (False, reason): 拒绝
        """
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

        写入类 Ability 检查写入路径权限；
        读取类 Ability 检查读取路径权限；
        命令类 Ability 检查命令安全性 + 工作目录权限；
        其他 Ability 无路径安全关注，返回 ALLOW（由 HITLPolicy 决定是否需要 HITL）。
        """
        if ability_name in self.COMMAND_ABILITIES and tool_args:
            return self._check_command(ability_name, tool_args)

        if ability_name in self.WRITE_ABILITIES and tool_args:
            paths = self._extract_paths(ability_name, tool_args)
            if paths:
                return self._check_write_paths(ability_name, paths)

        if ability_name in self.READ_ABILITIES and tool_args:
            paths = self._extract_paths(ability_name, tool_args)
            if paths:
                return self._check_read_paths(ability_name, paths)

        return PermissionVerdict(
            decision=PermissionDecision.ALLOW,
            reason="no_path_security_concern",
        )

    def _check_write_paths(self, ability_name: str, paths: list[str]) -> PermissionVerdict:
        for path in paths:
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

    def _check_read_paths(self, ability_name: str, paths: list[str]) -> PermissionVerdict:
        for path in paths:
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
    ) -> PermissionVerdict:
        """检查命令类 Ability 权限。

        命令安全检查逻辑：
        - 工作目录：如果在 workspace 外且不在 allowed_paths → DENY
        - 命令安全性：委托 CommandSafetyChecker（含子命令路由）
        - SAFE → ALLOW
        - DANGEROUS → DENY
        - REQUIRE_HITL → REQUIRE_HITL
        """
        command = tool_args.get("command", "")
        if not command:
            return PermissionVerdict(
                decision=PermissionDecision.DENY,
                reason="Empty command",
                metadata={"ability_name": ability_name},
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
        elif verdict.category == CommandSafetyCategory.DANGEROUS:
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

    @staticmethod
    def _extract_paths(ability_name: str, tool_args: dict[str, Any]) -> list[str]:
        paths: list[str] = []
        if ability_name == "move_file":
            src = tool_args.get("file_path")
            dst = tool_args.get("destination_path")
            if src:
                paths.append(src)
            if dst:
                paths.append(dst)
        elif ability_name == "execute_command":
            wd = tool_args.get("working_dir")
            if wd:
                paths.append(wd)
        else:
            path = tool_args.get("file_path")
            if path:
                paths.append(path)
        return paths

    @property
    def allowed_paths(self) -> list[str] | None:
        return self._allowed_paths

    @property
    def workspace_root(self) -> str | None:
        return self._workspace_root
