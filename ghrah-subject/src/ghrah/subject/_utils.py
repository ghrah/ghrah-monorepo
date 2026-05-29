from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ghrah.abilities._utils import is_subpath


@dataclass(frozen=True)
class AbilityPathSpec:
    """Ability 的路径参数规格，用于路径提取和权限检查。

    Attributes:
        path_keys: 文件/目录路径参数名（有序），如 ("file_path",) 或 ("source_path", "destination_path")
        working_dir_keys: 工作目录参数名，如 ("working_dir",)
        alt_keys: 主参数名到备选参数名的映射，如 {"source_path": "file_path"} 表示先找 source_path，找不到则找 file_path
    """

    path_keys: tuple[str, ...] = ()
    working_dir_keys: tuple[str, ...] = ()
    alt_keys: dict[str, str] | None = None


ABILITY_PATH_SPECS: dict[str, AbilityPathSpec] = {
    "read_file": AbilityPathSpec(path_keys=("file_path",)),
    "write_file": AbilityPathSpec(path_keys=("file_path",)),
    "edit_file": AbilityPathSpec(path_keys=("file_path",)),
    "delete_file": AbilityPathSpec(path_keys=("file_path",)),
    "list_directory": AbilityPathSpec(path_keys=("dir_path",)),
    "move_file": AbilityPathSpec(
        path_keys=("source_path", "destination_path"),
        alt_keys={"source_path": "file_path"},
    ),
    "execute_command": AbilityPathSpec(working_dir_keys=("working_dir",)),
}


_FALLBACK_PATH_KEYS = ("file_path", "dir_path", "working_dir")


def extract_paths(ability_name: str, tool_args: dict[str, Any]) -> list[str]:
    """从 tool_args 中提取 Ability 涉及的所有路径（文件路径 + 工作目录路径）。

    已知 Ability 使用 ABILITY_PATH_SPECS 注册表提取；
    未知 Ability 回退到常见路径参数名（file_path, dir_path, working_dir）。

    Args:
        ability_name: Ability 名称
        tool_args: 工具调用参数

    Returns:
        提取到的路径列表（不含空值）
    """
    spec = ABILITY_PATH_SPECS.get(ability_name)
    if spec is not None:
        paths: list[str] = []
        alt_keys = spec.alt_keys or {}
        for key in spec.path_keys:
            value = tool_args.get(key) or tool_args.get(alt_keys.get(key, ""))
            if value and isinstance(value, str):
                paths.append(value)
        for key in spec.working_dir_keys:
            value = tool_args.get(key)
            if value and isinstance(value, str):
                paths.append(value)
        return paths
    paths = []
    for key in _FALLBACK_PATH_KEYS:
        value = tool_args.get(key)
        if value and isinstance(value, str):
            paths.append(value)
            break
    return paths


__all__ = ["is_subpath", "AbilityPathSpec", "ABILITY_PATH_SPECS", "extract_paths"]
