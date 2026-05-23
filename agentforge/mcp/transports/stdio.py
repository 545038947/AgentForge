"""Stdio Transport - 通过进程 stdin/stdout 与 MCP Server 通信。"""

import asyncio
import json
import os
import signal
import subprocess
import sys
from typing import Any, Dict, Optional

from agentforge.mcp.errors import MCPConnectionError
from agentforge.mcp.transport import MCPTransport


class StdioTransport(MCPTransport):
    """通过进程标准输入输出与 MCP Server 通信的传输层。

    针对 Windows 平台的特殊处理：
    - Windows 上 asyncio subprocess 在事件循环关闭后会有清理问题
    - 使用安全的同步清理方法来避免 RuntimeError
    """

    def __init__(
        self,
        command: str,
        args: list = None,
        env: Dict[str, str] = None,
    ):
        """
        初始化 Stdio Transport。

        Args:
            command: MCP Server 可执行命令
            args: 命令行参数
            env: 环境变量
        """
        self.command = command
        self.args = args or []
        self.env = env or {}

        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 0

        # 保存 PID 用于同步清理
        self._pid: Optional[int] = None

    async def connect(self) -> None:
        """启动 MCP Server 进程并建立连接。"""
        try:
            # 构建完整环境变量
            full_env = os.environ.copy()
            full_env.update(self.env)

            # 启动进程
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
            )

            # 保存 PID
            self._pid = self._process.pid

            self._reader = self._process.stdout
            self._writer = self._process.stdin

        except Exception as e:
            raise MCPConnectionError(f"Failed to start MCP Server: {e}") from e

    async def request(
        self, method: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """发送 JSON-RPC 请求并等待响应。"""
        if not self.is_connected():
            raise MCPConnectionError("Not connected to MCP Server")

        # 构建请求
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        try:
            # 发送请求（以换行符结束）
            request_str = json.dumps(request) + "\n"
            self._writer.write(request_str.encode("utf-8"))
            await self._writer.drain()

            # 读取响应
            response_line = await self._reader.readline()
            if not response_line:
                raise MCPConnectionError("MCP Server closed connection")

            response = json.loads(response_line.decode("utf-8"))

            # 检查错误
            if "error" in response:
                error = response["error"]
                raise MCPConnectionError(
                    f"MCP Error {error.get('code')}: {error.get('message')}"
                )

            return response.get("result", {})

        except json.JSONDecodeError as e:
            raise MCPConnectionError(f"Invalid JSON response: {e}") from e
        except Exception as e:
            if isinstance(e, MCPConnectionError):
                raise
            raise MCPConnectionError(f"Request failed: {e}") from e

    async def send_notification(
        self, method: str, params: Dict[str, Any] = None
    ) -> None:
        """发送 JSON-RPC 通知（无需等待响应）。"""
        if not self.is_connected():
            raise MCPConnectionError("Not connected to MCP Server")

        # 构建通知（无 id 字段）
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }

        try:
            # 发送通知（以换行符结束）
            notification_str = json.dumps(notification) + "\n"
            self._writer.write(notification_str.encode("utf-8"))
            await self._writer.drain()

        except Exception as e:
            raise MCPConnectionError(f"Failed to send notification: {e}") from e

    async def close(self) -> None:
        """关闭连接并终止进程。

        使用安全的清理顺序，避免 Windows 上的 asyncio subprocess 清理问题。
        """
        # 先清理引用，防止其他地方访问
        writer = self._writer
        reader = self._reader
        process = self._process
        pid = self._pid

        self._writer = None
        self._reader = None
        self._process = None
        self._pid = None

        # 异步关闭 writer
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except (OSError, ConnectionError, BrokenPipeError, RuntimeError):
                pass

        # 异步尝试优雅终止
        if process:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                # 超时后使用同步方式强制终止
                self._force_kill_sync(pid)
            except (OSError, ProcessLookupError):
                # 其他异常也尝试同步强制终止
                self._force_kill_sync(pid)

        # 如果异步清理失败，使用同步方式作为后备
        if pid and self._is_process_alive(pid):
            self._force_kill_sync(pid)

    def _is_process_alive(self, pid: int) -> bool:
        """检查进程是否仍在运行。"""
        try:
            if sys.platform == "win32":
                # Windows: 使用 tasklist 检查
                import subprocess
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return str(pid) in result.stdout
            else:
                # Unix: 使用 os.kill(pid, 0) 检查
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, OSError):
            return False
        except (OSError, subprocess.SubprocessError, PermissionError):
            return False

    def _force_kill_sync(self, pid: Optional[int]) -> None:
        """使用同步方式强制终止进程。

        这是后备清理方法，用于处理 Windows 上 asyncio 事件循环关闭后的清理问题。
        """
        if not pid:
            return

        try:
            if sys.platform == "win32":
                # Windows: 使用 taskkill 强制终止
                import subprocess
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                )
            else:
                # Unix: 使用 SIGKILL
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            # 进程已经不存在
            pass
        except (OSError, subprocess.SubprocessError, PermissionError):
            # 忽略其他错误（进程可能已经终止）
            pass

    def is_connected(self) -> bool:
        """检查是否已连接。"""
        return (
            self._process is not None
            and self._process.returncode is None
            and self._reader is not None
            and self._writer is not None
        )