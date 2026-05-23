"""Stdio Transport - 通过进程 stdin/stdout 与 MCP Server 通信。"""

import asyncio
import json
import uuid
from typing import Any, Dict, Optional

from agentforge.mcp.errors import MCPConnectionError
from agentforge.mcp.transport import MCPTransport


class StdioTransport(MCPTransport):
    """通过进程标准输入输出与 MCP Server 通信的传输层。"""

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

    async def connect(self) -> None:
        """启动 MCP Server 进程并建立连接。"""
        try:
            # 构建完整环境变量
            import os
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
        """关闭连接并终止进程。"""
        # 先清理引用，防止其他地方访问
        writer = self._writer
        process = self._process
        self._writer = None
        self._reader = None
        self._process = None

        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        if process:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
            except Exception:
                pass

    def is_connected(self) -> bool:
        """检查是否已连接。"""
        return (
            self._process is not None
            and self._process.returncode is None
            and self._reader is not None
            and self._writer is not None
        )
