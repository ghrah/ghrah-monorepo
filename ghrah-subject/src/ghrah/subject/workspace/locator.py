# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Workspace locator 工具：本地路径 ↔ file:// URI 互转。

从 legacy GitWorkspaceProvider 平移至此（provider 删除后 locator 语义与
物理后端解耦，纯路径工具独立成模块）。行为原样保留：

- ``path_to_locator``：``Path.as_uri()`` 规范形态（POSIX ``file:///abs/path``）；
- ``locator_to_path``：file:// → 本地绝对路径，兼容旧式盘符 netloc 与
  裸反斜杠拼接形态；非 file:// locator 抛 ValueError。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

__all__ = ["locator_to_path", "path_to_locator"]

_DRIVE_NETLOC_RE = re.compile(r"^[A-Za-z]:$")


def path_to_locator(path: str) -> str:
    """本地绝对路径 → file:// URI（``Path.as_uri()`` 规范形态）。

    POSIX 上输出 ``file:///abs/path``（与历史拼接格式逐字节一致）；
    Windows 上输出 ``file:///C:/ws/a``（正斜杠 + 百分号编码），保证
    round-trip 与 URI 合法性。
    """
    return Path(os.path.abspath(path)).as_uri()


def locator_to_path(locator: str) -> str:
    """file:// URI → 本地绝对路径。

    非 file:// locator（未来 nfs://、table://）抛 ValueError。

    兼容两类历史/宽松输入：
    - ``file://C:/x``（盘符落在 netloc 的旧式 Windows 形态）；
    - ``file://C:\\x``（未转义反斜杠的裸拼接形态）。

    UNC（``file://server/share/x``，由 ``as_uri`` 产出）仅 Windows 上还原为
    ``\\\\server\\share\\x``；POSIX 上拒绝远程主机 netloc（localhost 除外）。
    """
    parsed = urlparse(locator)
    if parsed.scheme != "file":
        raise ValueError(f"file:// locator required, got: {locator}")
    path = unquote(parsed.path or "")
    netloc = unquote(parsed.netloc or "")
    if (
        os.name == "nt"
        and len(path) > 2
        and path[0] == "/"
        and path[1].isalpha()
        and path[2] == ":"
    ):
        # as_uri 规范形态 file:///C:/x 反解得 /C:/x；剥前导斜杠还原盘符，
        # 否则 Path('/C:/x') → \C:\x 且 is_absolute()=False。
        path = path[1:]
    if netloc:
        if _DRIVE_NETLOC_RE.match(netloc):
            # 旧式盘符形态：file://C:/x → /C:/x（Path 归一为 C:\x）
            path = f"/{netloc}{path}"
        elif "\\" in netloc:
            # 宽容：file://C:\ws\a 裸拼接形态
            path = netloc + path
        elif netloc == "localhost":
            pass
        elif os.name == "nt":
            # UNC：file://server/share/x → //server/share/x
            path = f"//{netloc}{path}"
        else:
            raise ValueError(
                f"file:// locator with remote host is not locally resolvable: {locator}"
            )
    if not path:
        return ""
    return str(Path(path))
