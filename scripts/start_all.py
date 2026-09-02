# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""ghrah 全栈一键启动脚本（单进程架构）。

拓扑（C5 单进程化后，Core 不再独立进程/端口）::

    ghrah-subject (uvicorn, :4112) ← 内嵌 Core（Ouroboros 装配，CoreUnit 懒挂载）
    Observer WebUI (vite dev server, :5173) --WS--> ws://localhost:4112/ws

组件：

1. subject — ``uv run ghrah-subject-server``：Python 后端全家桶（Ouroboros 装配
   内嵌 Core + uvicorn 挂 Observer WS/HTTP，默认 :4112）。
2. webui   — ``pnpm dev``：observer-web 前端 dev server（``--no-webui`` 跳过）。

webui 通过注入 ``packages/observer-web/.env.local``（``VITE_GHRAH_SUBJECT_WS_URL``）
感知后端地址，退出时清理该文件；自定义 ``--subject-port`` 时前端自动跟随。

使用方式::

    python scripts/start_all.py                  # 全栈（后端 + 前端 dev server）
    python scripts/start_all.py --no-webui       # 仅后端
    python scripts/start_all.py --webui-port 5174
    python scripts/start_all.py --open           # 启动后打开浏览器

前置要求：``uv``（Python 侧）；webui 另需 Node.js >= 22 与 pnpm >= 9
（pnpm 11 依赖 node:sqlite，Node 20 下直接崩溃）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

logger = logging.getLogger("ghrah.start_all")

MONOREPO_ROOT = Path(__file__).resolve().parent.parent
WEBUI_PACKAGE_DIR = MONOREPO_ROOT / "ghrah-observer-webui" / "packages" / "observer-web"
WEBUI_ENV_FILE = ".env.local"
WEBUI_ENV_KEY = "VITE_GHRAH_SUBJECT_WS_URL"

DEFAULT_SUBJECT_PORT = 4112
DEFAULT_WEBUI_PORT = 5173


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="ghrah 全栈一键启动（subject 内嵌 Core + observer-web dev server）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("GHRAH_SUBJECT_SERVER_HOST", "127.0.0.1"),
        help="服务监听地址（默认: 127.0.0.1）",
    )
    parser.add_argument(
        "--subject-port",
        type=int,
        default=int(os.environ.get("GHRAH_SUBJECT_SERVER_PORT", str(DEFAULT_SUBJECT_PORT))),
        help=f"Subject（Observer WS）端口（默认: {DEFAULT_SUBJECT_PORT}）",
    )
    parser.add_argument(
        "--webui-port",
        type=int,
        default=int(os.environ.get("GHRAH_WEBUI_PORT", str(DEFAULT_WEBUI_PORT))),
        help=f"WebUI dev server 端口（默认: {DEFAULT_WEBUI_PORT}）",
    )
    parser.add_argument("--no-webui", action="store_true", help="不启动 WebUI dev server")
    parser.add_argument("--open", action="store_true", help="就绪后打开浏览器")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="脚本自身日志级别（默认: INFO）",
    )
    return parser.parse_args()


def port_in_use(host: str, port: int) -> bool:
    """探测 host:port 是否有服务监听（loopback 双栈：IPv4 + IPv6）。"""
    probes: list[tuple[socket.AddressFamily, tuple[str, int]]] = [(socket.AF_INET, (host, port))]
    if host in ("localhost", "127.0.0.1"):
        probes.append((socket.AF_INET6, ("::1", port)))
    for family, addr in probes:
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                if sock.connect_ex(addr) == 0:
                    return True
        except OSError:
            continue
    return False


def check_port_free(host: str, port: int, name: str) -> None:
    """启动前检查端口占用，给出可操作的报错信息。"""
    if port_in_use(host, port):
        raise RuntimeError(
            f"{name} 端口 {port} 已被占用——多半是上一次的进程还活着"
            f"（可用 `ss -ltnp | grep {port}` 找到后停止，或换 --subject-port/--webui-port）。"
        )


def ensure_tool(name: str, hint: str) -> str:
    """确认工具在 PATH 上并返回其路径。"""
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"`{name}` 不在 PATH 上；{hint}")
    return path


def ensure_node_version() -> None:
    """pnpm 11 依赖 node:sqlite（Node 22+ 才有），Node 20 下任何 pnpm 命令直接崩。"""
    node = ensure_tool("node", "webui 需要 Node.js 工具链。")
    out = subprocess.run(
        [node, "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    try:
        major = int(out.lstrip("v").split(".", maxsplit=1)[0])
    except ValueError:
        raise RuntimeError(f"无法解析 node 版本号：{out!r}") from None
    if major < 22:
        raise RuntimeError(
            f"node {out} 过旧：pnpm 11 需要 node >= 22（node:sqlite），请 `nvm use 24` 后重试"
        )


def wait_port_open(host: str, port: int, timeout: float, name: str) -> None:
    """轮询等待端口就绪；超时仅告警不硬失败（服务可能仍在启动）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_in_use(host, port):
            logger.info("%s 已就绪（端口 %d）", name, port)
            return
        time.sleep(0.5)
    logger.warning("%s 在 %.0fs 内未就绪（可能仍在启动，继续运行）", name, timeout)


def spawn(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen[Any]:
    """启动子进程（独立进程组，便于整组终止）；输出直通终端。"""
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, cwd=str(cwd), env=env, **kwargs)


def terminate(proc: subprocess.Popen[Any], name: str) -> None:
    """终止子进程：对进程组先 SIGTERM，5s 不退再 SIGKILL。

    spawn() 已将子进程放入独立进程组（start_new_session），而子进程还会
    继续派生孙进程（pnpm → sh → vite 三层链）——只 kill 直接子进程会留下
    孤儿 vite，必须整组终止。直接子进程已退出时仍对组做一次清扫，
    兜住「父死子活」的孤儿形态。
    """
    if os.name == "nt":  # pragma: no cover - Windows 分支（无进程组）
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        logger.info("%s 已停止", name)
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("%s 未响应 SIGTERM，强制 SIGKILL", name)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("%s 进程组未能完全终止（可能有外部进程驻留）", name)
            return
    logger.info("%s 已停止", name)


async def wait_shutdown_signal() -> None:
    """等待 SIGINT/SIGTERM（Windows 无 add_signal_handler，靠 KeyboardInterrupt）。"""
    shutdown = asyncio.Event()
    if os.name != "nt":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown.set)
        await shutdown.wait()
    else:  # pragma: no cover - Windows 分支
        await asyncio.Event().wait()


def write_webui_env(subject_ws_url: str) -> Path:
    """写入 webui env 文件（vite 只在启动时读取，必须先于 pnpm dev 落盘）。"""
    path = WEBUI_PACKAGE_DIR / WEBUI_ENV_FILE
    path.write_text(f"{WEBUI_ENV_KEY}={subject_ws_url}\n", encoding="utf-8")
    logger.info("webui env 注入: %s=%s", WEBUI_ENV_KEY, subject_ws_url)
    return path


def cleanup_webui_env(path: Path | None) -> None:
    """退出时清理注入的 env 文件，避免污染后续手动启动的 vite。"""
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.debug("webui env 清理失败", exc_info=True)
    logger.info("webui env 已清理")


async def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    uv = ensure_tool("uv", "Python 侧经 uv 运行（https://docs.astral.sh/uv/）。")
    if not args.no_webui:
        ensure_tool("pnpm", "webui 需要 pnpm >= 9（https://pnpm.io/installation）。")
        ensure_node_version()
        if not WEBUI_PACKAGE_DIR.is_dir():
            raise RuntimeError(f"observer-web 包不存在：{WEBUI_PACKAGE_DIR}")

    check_port_free(args.host, args.subject_port, "Subject")
    if not args.no_webui:
        check_port_free(args.host, args.webui_port, "WebUI")

    procs: list[tuple[str, subprocess.Popen[Any]]] = []
    webui_env_path: Path | None = None
    exit_code = 0
    try:
        # ── 1. Subject（内嵌 Core + Observer WS 服务） ──
        subject_env = os.environ.copy()
        subject_env["GHRAH_SUBJECT_SERVER_PORT"] = str(args.subject_port)
        subject_env.setdefault("GHRAH_SUBJECT_SERVER_HOST", args.host)
        subject = spawn([uv, "run", "ghrah-subject-server"], cwd=MONOREPO_ROOT, env=subject_env)
        procs.append(("Subject", subject))
        logger.info(
            "Subject 启动中（pid=%d, ws://%s:%d/ws）...",
            subject.pid,
            args.host,
            args.subject_port,
        )
        wait_port_open(args.host, args.subject_port, timeout=20, name="Subject")
        if subject.poll() is not None:
            raise RuntimeError(
                f"Subject 进程提前退出（code={subject.returncode}），请查看上方日志。"
            )

        # ── 2. WebUI dev server ──
        if not args.no_webui:
            webui_env_path = write_webui_env(f"ws://{args.host}:{args.subject_port}/ws")
            webui = spawn(
                ["pnpm", "dev", "--port", str(args.webui_port), "--strictPort"],
                cwd=WEBUI_PACKAGE_DIR,
            )
            procs.append(("WebUI", webui))
            logger.info(
                "WebUI dev server 启动中（pid=%d, http://localhost:%d）...",
                webui.pid,
                args.webui_port,
            )
            wait_port_open(args.host, args.webui_port, timeout=20, name="WebUI")
            if webui.poll() is not None:
                raise RuntimeError(
                    f"WebUI dev server 提前退出（code={webui.returncode}）；"
                    "常见原因：依赖未装（在 ghrah-observer-webui/ 下 `pnpm install`）或端口被占。"
                )

        logger.info("=== ghrah 全栈启动完成，Ctrl+C 退出 ===")
        if args.open:
            url = f"http://localhost:{args.webui_port}"
            webbrowser.open(url)
            logger.info("浏览器已打开 %s", url)

        await wait_shutdown_signal()
    except KeyboardInterrupt:
        logger.info("收到中断，开始退出…")
    except RuntimeError as exc:
        logger.error("%s", exc)
        exit_code = 1
    finally:
        for name, proc in reversed(procs):
            try:
                terminate(proc, name)
            except Exception:  # noqa: BLE001 - 退出清理尽力而为
                logger.debug("%s 终止失败", name, exc_info=True)
        cleanup_webui_env(webui_env_path)
        logger.info("=== ghrah 全栈已关闭 ===")

    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
