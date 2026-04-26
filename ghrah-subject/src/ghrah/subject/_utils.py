from __future__ import annotations

import os

__all__ = ["is_subpath"]


def is_subpath(path: str, parent: str) -> bool:
    """检查 path 是否在 parent 目录下（严格前缀匹配，防止 /tmp/data 匹配 /tmp/database）。

    Args:
        path: 待检查的路径
        parent: 父目录路径

    Returns:
        True 如果 path 是 parent 或 parent 的子路径
    """
    path_abs = os.path.abspath(path)
    parent_abs = os.path.abspath(parent)
    if parent_abs == path_abs:
        return True
    return path_abs.startswith(parent_abs + os.sep)
