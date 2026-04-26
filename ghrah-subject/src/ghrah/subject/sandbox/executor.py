from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field

from ghrah.subject._utils import is_subpath

__all__ = ["SandboxExecutor", "SandboxExecutorConfig", "CommandResult"]


@dataclass
class CommandResult:
    """命令执行结果。"""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    command: list[str] = field(default_factory=list)
    cwd: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class SandboxExecutorConfig:
    """SandboxExecutor 配置。

    Attributes:
        default_timeout: 默认命令超时（秒）
        max_output_bytes: 单个输出流最大字节数
        blocked_commands: 被阻止的基础命令名集合
        env_overrides: 额外环境变量覆盖
    """

    default_timeout: float = 300.0
    max_output_bytes: int = 1_000_000
    blocked_commands: set[str] = field(default_factory=lambda: {
        "rm", "rmdir", "mkfs", "dd", "format",
        "shutdown", "reboot", "kill", "killall",
    })
    env_overrides: dict[str, str] = field(default_factory=dict)


class SandboxExecutor:
    """沙箱命令执行器。

    使用 asyncio.create_subprocess_exec 执行命令，
    绝对禁止在主线程阻塞。

    职责：
    - 命令安全检查（blocked commands）
    - 工作目录约束（cwd 限制在 workspace_root 内）
    - 超时控制
    - 输出截断
    - 环境变量注入
    """

    def __init__(
        self,
        workspace_root: str,
        config: SandboxExecutorConfig | None = None,
    ) -> None:
        self._workspace_root = os.path.abspath(workspace_root)
        self._config = config or SandboxExecutorConfig()
        self._started = False

    async def start(self) -> None:
        """启动执行器（创建 workspace_root 目录等初始化）。"""
        os.makedirs(self._workspace_root, exist_ok=True)
        self._started = True

    async def stop(self) -> None:
        """停止执行器。"""
        self._started = False

    @property
    def workspace_root(self) -> str:
        return self._workspace_root

    @property
    def config(self) -> SandboxExecutorConfig:
        return self._config

    async def execute_command(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        stdin_data: str | None = None,
    ) -> CommandResult:
        """执行命令并等待结果。

        Args:
            command: 命令及参数列表
            cwd: 工作目录（相对于 workspace_root 或绝对路径）
            timeout: 超时秒数，None 使用默认值
            env: 额外环境变量
            stdin_data: 传入 stdin 的数据

        Returns:
            CommandResult
        """
        if not self._started:
            raise RuntimeError("SandboxExecutor not started")

        allowed, reason = self.check_command(command)
        if not allowed:
            return CommandResult(
                exit_code=-1, stdout="", stderr=reason,
                command=command, cwd=cwd or "",
            )

        resolved_cwd = self._resolve_cwd(cwd)
        effective_timeout = timeout or self._config.default_timeout
        full_env = self._build_env(env)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=resolved_cwd,
                env=full_env,
                stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=stdin_data.encode() if stdin_data else None),
                timeout=effective_timeout,
            )
            exit_code = process.returncode if process.returncode is not None else -1

            stdout, stdout_truncated = self._truncate_output(
                stdout_bytes, self._config.max_output_bytes
            )
            stderr_text, stderr_truncated = self._truncate_output(
                stderr_bytes, self._config.max_output_bytes
            )

            if stdout_truncated:
                stderr_text += (
                    f"\n[stdout truncated at {self._config.max_output_bytes} bytes]"
                )
            if stderr_truncated:
                stderr_text += (
                    f"\n[stderr truncated at {self._config.max_output_bytes} bytes]"
                )

            return CommandResult(
                exit_code=exit_code, stdout=stdout, stderr=stderr_text,
                command=command, cwd=cwd or "",
            )

        except TimeoutError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            return CommandResult(
                exit_code=-1, stdout="", stderr=f"Command timed out after {effective_timeout}s",
                timed_out=True, command=command, cwd=cwd or "",
            )
        except Exception as e:
            return CommandResult(
                exit_code=-1, stdout="", stderr=str(e),
                command=command, cwd=cwd or "",
            )

    def check_command(self, command: list[str]) -> tuple[bool, str]:
        """检查命令是否允许执行。

        Returns:
            (allowed, reason)
        """
        if not command:
            return False, "Empty command"
        base = os.path.basename(command[0])
        if base in self._config.blocked_commands:
            return False, f"Command blocked: {base}"
        return True, ""

    def _resolve_cwd(self, cwd: str | None) -> str:
        """将 cwd 解析为绝对路径，确保在 workspace_root 内。"""
        if cwd is None:
            return self._workspace_root
        if os.path.isabs(cwd):
            abs_cwd = cwd
        else:
            abs_cwd = os.path.abspath(os.path.join(self._workspace_root, cwd))
        if not is_subpath(abs_cwd, self._workspace_root) and abs_cwd != self._workspace_root:
            raise ValueError(
                f"cwd '{cwd}' resolves to '{abs_cwd}' which is outside "
                f"workspace_root '{self._workspace_root}'"
            )
        return abs_cwd

    def _build_env(self, extra: dict[str, str] | None) -> dict[str, str]:
        """构建子进程环境变量。"""
        env = dict(os.environ)
        env.update(self._config.env_overrides)
        if extra:
            env.update(extra)
        return env

    @staticmethod
    def _truncate_output(data: bytes, max_bytes: int) -> tuple[str, bool]:
        """截断输出到 max_bytes，返回 (text, truncated)。"""
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = str(data)
        if len(data) > max_bytes:
            return text[:max_bytes], True
        return text, False
