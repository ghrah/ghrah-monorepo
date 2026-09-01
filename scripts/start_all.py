#!/usr/bin/env python3
"""ghrah 全栈启动脚本。

一键启动 Core（内含 SupervisorActor）→ Subject（+ Observer TUI）。

新架构拓扑：
    Core (WebSocket server, port 4111) ← Subject (WebSocket client)
    Subject (WebSocket server, port 4112) ← Observer (WebSocket client)

使用方式：
    python scripts/start_all.py                          # 默认配置
    python scripts/start_all.py --core-port 9000         # 自定义 Core 端口
    python scripts/start_all.py --no-tui                 # 不启动 Observer TUI
    python scripts/start_all.py --no-subject             # 不启动 Subject
    python scripts/start_all.py --core-port 9000 --no-tui

所有组件也支持通过环境变量配置：
    GHRAH_CORE_PORT=8080
    GHRAH_CORE_HOST=0.0.0.0
    GHRAH_SUBJECT_CORE_URL=ws://localhost:8080/ws
    GHRAH_SUBJECT_WORKSPACE_ROOT=~/ghrah-workspace
    GHRAH_SUBJECT_DB_PATH=~/.ghrah/subject.db
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time

logger = logging.getLogger("ghrah.startup")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ghrah 全栈启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--core-port",
        type=int,
        default=int(os.environ.get("GHRAH_CORE_PORT", "4111")),
        help="Core 服务监听端口 (默认: 4111)",
    )
    parser.add_argument(
        "--subject-port",
        type=int,
        default=int(os.environ.get("GHRAH_SUBJECT_SERVER_PORT", "4112")),
        help="Subject 服务监听端口 (默认: 4112)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("GHRAH_CORE_HOST", "127.0.0.1"),
        help="服务监听地址 (默认: 127.0.0.1)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.environ.get("GHRAH_CORE_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认: INFO)",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="不启动 Observer TUI",
    )
    parser.add_argument(
        "--no-subject",
        action="store_true",
        help="不启动 Subject",
    )
    return parser.parse_args()


def _connect_host(host: str) -> str:
    if host == "0.0.0.0":
        return "127.0.0.1"
    return host


def get_core_ws_url(host: str, port: int) -> str:
    return f"ws://{_connect_host(host)}:{port}/ws"


def get_core_http_url(host: str, port: int) -> str:
    return f"http://{_connect_host(host)}:{port}/health"


def get_subject_ws_url(host: str, port: int) -> str:
    return f"ws://{_connect_host(host)}:{port}/ws"


async def wait_for_server(url: str, timeout: float = 15.0, name: str = "Server") -> None:
    import aiohttp

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None

    while time.monotonic() < deadline:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info("%s is ready: %s", name, data)
                        return
        except Exception as e:
            last_exc = e
            await asyncio.sleep(0.5)

    raise TimeoutError(
        f"{name} at {url} did not become ready within {timeout}s. "
        f"Last error: {last_exc}"
    )


async def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    core_ws_url = get_core_ws_url(args.host, args.core_port)
    core_http_url = get_core_http_url(args.host, args.core_port)
    subject_ws_url = get_subject_ws_url(args.host, args.subject_port)

    logger.info("=== ghrah 全栈启动 ===")
    logger.info("  Core server: %s (ws: %s)", core_http_url, core_ws_url)
    logger.info("  Subject server ws: %s", subject_ws_url)
    logger.info("  Observer TUI: %s", "disabled" if args.no_tui else "enabled")
    logger.info("  Subject client: %s", "disabled" if args.no_subject else "enabled")

    # ── 1. 启动 Core 服务（内含 SupervisorActor + WebSocket server） ──
    import uvicorn
    from ghrah.core.server.app import create_app
    from ghrah.core.server.config import CoreServerConfig

    core_config = CoreServerConfig(
        host=args.host,
        port=args.core_port,
        log_level=args.log_level,
    )
    core_app = create_app(core_config)
    core_server_config = uvicorn.Config(
        core_app,
        host=args.host,
        port=args.core_port,
        log_level=args.log_level.lower(),
        ws_ping_interval=30,
        ws_ping_timeout=10,
    )
    core_server = uvicorn.Server(core_server_config)

    core_task = asyncio.create_task(core_server.serve(), name="core-server")
    logger.info("Core server starting on %s:%d ...", args.host, args.core_port)

    try:
        await wait_for_server(core_http_url, timeout=15.0, name="Core server")
    except TimeoutError as e:
        logger.error(str(e))
        sys.exit(1)

    # ── 2. 启动 Subject（client 连接 Core + server 接受 Observer） ──
    subject_engine = None
    subject_server = None
    subject_task = None
    if not args.no_subject:
        from ghrah.subject.config import (
            CoreConnectionConfig,
            HITLPolicyConfig,
            SubjectConfig,
        )
        from ghrah.subject.runtime.engine import SubjectEngine
        from ghrah.subject.server.app import create_app as create_subject_app
        from ghrah.subject.server.config import ObserverServerConfig

        subject_config = SubjectConfig(
            workspace_root=os.environ.get(
                "GHRAH_SUBJECT_WORKSPACE_ROOT",
                os.path.expanduser("~/ghrah-workspace"),
            ),
            db_path=os.environ.get(
                "GHRAH_SUBJECT_DB_PATH",
                os.path.expanduser("~/.ghrah/subject.db"),
            ),
            hitl_policy=HITLPolicyConfig(
                auto_approve_abilities=[
                    ab.strip()
                    for ab in os.environ.get(
                        "GHRAH_SUBJECT_HITL_AUTO_APPROVE_ABILITIES",
                        "",
                    ).split(",")
                    if ab.strip()
                ],
                require_approval_by_default=True,
            ),
            core=CoreConnectionConfig(
                url=core_ws_url,
                command_timeout=300,
            ),
        )

        subject_engine = SubjectEngine(subject_config)
        subject_engine.register_builtin_units(profile="full")
        subject_engine.discover()
        subject_engine.enable_from_config()
        subject_engine.validate()
        await subject_engine.start()
        logger.info("SubjectEngine started (profile=full, connected to Core)")

        observer_config = ObserverServerConfig(
            host=args.host,
            port=args.subject_port,
            log_level=args.log_level,
        )
        subject_app = create_subject_app(observer_config, engine=subject_engine)
        subject_server_config = uvicorn.Config(
            subject_app,
            host=args.host,
            port=args.subject_port,
            log_level=args.log_level.lower(),
            ws_ping_interval=30,
            ws_ping_timeout=10,
        )
        subject_server = uvicorn.Server(subject_server_config)
        subject_task = asyncio.create_task(subject_server.serve(), name="subject-server")
        logger.info("Subject observer server starting on %s:%d ...", args.host, args.subject_port)

        subject_http_url = f"http://{_connect_host(args.host)}:{args.subject_port}/health"
        try:
            await wait_for_server(subject_http_url, timeout=10.0, name="Subject server")
        except TimeoutError:
            logger.warning("Subject server health check not available (may still be starting)")

    # ── 3. 启动 Observer TUI（子进程） ──
    tui_process = None
    if not args.no_tui:
        tui_cwd = os.path.join(os.path.dirname(__file__), "..", "ghrah-observer-tui")
        env = os.environ.copy()
        env["GHRAH_SUBJECT_SERVER_URL"] = subject_ws_url

        tui_process = subprocess.Popen(
            ["uv", "run", "ghrah-observer-tui"],
            cwd=os.path.abspath(tui_cwd),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Observer TUI started (pid=%d)", tui_process.pid)

    # ── 4. 等待关闭信号 ──
    logger.info("=== 全栈启动完成，按 Ctrl+C 退出 ===")

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        logger.info("Received shutdown signal, shutting down...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    await shutdown_event.wait()

    # ── 5. 优雅关闭 ──
    logger.info("Shutting down...")

    if tui_process is not None:
        tui_process.terminate()
        try:
            tui_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tui_process.kill()
        logger.info("Observer TUI stopped")

    if subject_server is not None:
        subject_server.should_exit = True
    if subject_task is not None:
        subject_task.cancel()
        try:
            await subject_task
        except asyncio.CancelledError:
            pass
        logger.info("Subject server stopped")

    if subject_engine is not None:
        await subject_engine.stop()
        logger.info("SubjectEngine stopped")

    core_server.should_exit = True
    core_task.cancel()
    try:
        await core_task
    except asyncio.CancelledError:
        pass
    logger.info("Core server stopped")

    logger.info("=== 全栈已关闭 ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
