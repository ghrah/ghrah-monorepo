# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""跨平台文件系统工具（Subject 内部共享）。

解决三个 POSIX 假设：
- 原子替换：写文件走 同目录 tmp + fsync + ``os.replace``。Windows 上目标被
  AV/索引器短暂占用时 ``os.replace`` 抛 ``PermissionError``，做小步重试。
- 只读内容删除：git object 等文件为只读，``shutil.rmtree`` 在 Windows 上删除
  只读项必抛 ``PermissionError``；onerror/onexc 回调先去只读再重试。
- 可写性探针：``os.access(path, os.W_OK)`` 在 Windows 不查 ACL，语义失真；
  用真实创建临时文件后删除的探针替代。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

__all__ = ["atomic_write_text", "is_writable", "robust_rmtree"]

_REPLACE_RETRIES = 5
_REPLACE_RETRY_DELAY_S = 0.05


def atomic_write_text(path: str | Path, content: str) -> None:
    """原子写文本文件（UTF-8）：同目录 tmp + fsync + os.replace。

    崩溃时不会留下半写目标文件；Windows 上目标被短暂锁定时重试
    ``_REPLACE_RETRIES`` 次（间隔 ``_REPLACE_RETRY_DELAY_S`` 秒）。

    Args:
        path: 目标文件路径（父目录不存在时自动创建）。
        content: 写入的文本内容。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp_path, target)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _replace_with_retry(src: Path, dst: Path) -> None:
    last_exc: PermissionError | None = None
    for _ in range(_REPLACE_RETRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:  # Windows: dst 被 AV/索引器占用
            last_exc = exc
            time.sleep(_REPLACE_RETRY_DELAY_S)
    assert last_exc is not None
    raise last_exc


def robust_rmtree(path: str | Path) -> None:
    """递归删除目录，容忍只读内容（git object 等）。

    非 POSIX 平台上删除只读文件/目录会抛 ``PermissionError``；此处经
    onerror/onexc 回调去只读（文件 0o600 / 目录 0o700）后重试，重试仍失败
    则抛出原异常（与无回调 rmtree 语义一致）。路径不存在时为 no-op。
    """
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=_onexc)  # type: ignore[call-overload]
    else:
        shutil.rmtree(p, onerror=_onerror)  # type: ignore[call-overload]


def _chmod_and_retry(func, path) -> bool:  # noqa: ANN001 — shutil 回调签名
    """对失败项去只读后重试原操作；成功返回 True。

    unlink/rmdir 需要父目录可写，故目标与父目录都去只读
    （目录 0o700 / 文件 0o600）。
    """
    try:
        parent = os.path.dirname(path)
        if parent and os.path.isdir(parent) and not os.access(parent, os.W_OK):
            os.chmod(parent, 0o700)
        if os.path.isdir(path) and not os.path.islink(path):
            os.chmod(path, 0o700)
        else:
            os.chmod(path, 0o600)
        func(path)
        return True
    except OSError:
        return False


def _onexc(func, path, excval) -> None:  # noqa: ANN001 — py3.12+ rmtree 回调
    if not _chmod_and_retry(func, path):
        raise excval


def _onerror(func, path, exc_info) -> None:  # noqa: ANN001 — py3.11 rmtree 回调
    if not _chmod_and_retry(func, path):
        raise exc_info[1].with_traceback(exc_info[2])


def is_writable(dir_path: str | Path) -> bool:
    """目录是否真实可写（创建临时文件后删除的探针）。

    替代 ``os.access(path, os.W_OK)``：后者在 Windows 上不查 ACL，语义失真。
    """
    try:
        fd, probe = tempfile.mkstemp(dir=str(dir_path))
    except OSError:
        return False
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(probe)
    except OSError:
        pass
    return True
