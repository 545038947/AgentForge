"""HTTP Transport - 通过 HTTP/SSE 与远程 MCP Server 通信。"""

import json
import logging
from typing import Any, Dict, Optional

import httpx

from hai_agent.mcp.errors import MCPConnectionError
from hai_agent.mcp.transport import MCPTransport

logger = logging.getLogger(__name__)


class HTTPTransport(MCPTransport):
    """通过 HTTP/SSE 与远程 MCP Server 通信的传输层。"""

    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ):
        """
        初始化 HTTP Transport。

        Args:
            url: MCP Server URL
            api_key: API Key（可选）
            headers: 自定义请求头
            timeout: 请求超时时间（秒）
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.custom_headers = headers or {}
        self.timeout = timeout

        self._client: Optional[httpx.AsyncClient] = None
        self._request_id = 0

    async def connect(self) -> None:
        """初始化 HTTP 客户端。"""
        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # 添加 API Key 认证
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # 合并自定义请求头
        headers.update(self.custom_headers)

        # 创建 HTTP 客户端
        self._client = httpx.AsyncClient(
            base_url=self.url,
            headers=headers,
            timeout=self.timeout,
        )

    async def request(
        self, method: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """发送 JSON-RPC 请求。"""
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
            # 发送 POST 请求
            response = await self._client.post(
                "/mcp",  # MCP 标准端点
                json=request,
            )

            # 检查 HTTP 状态
            if response.status_code != 200:
                raise MCPConnectionError(
                    f"HTTP Error {response.status_code}: {response.text}"
                )

            # 解析响应
            result = response.json()

            # 检查 JSON-RPC 错误
            if "error" in result:
                error = result["error"]
                raise MCPConnectionError(
                    f"MCP Error {error.get('code')}: {error.get('message')}"
                )

            return result.get("result", {})

        except httpx.HTTPError as e:
            raise MCPConnectionError(f"HTTP request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise MCPConnectionError(f"Invalid JSON response: {e}") from e
        except (httpx.HTTPError, OSError, ConnectionError, TimeoutError, json.JSONDecodeError) as e:
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
            # 发送 POST 请求（不等待响应）
            await self._client.post(
                "/mcp",
                json=notification,
            )

        except (OSError, ConnectionError, TimeoutError) as e:
            # 通知失败不抛出错误，只记录
            logger.debug(f"MCP 通知发送失败: {e}")

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def is_connected(self) -> bool:
        """检查是否已连接。"""
        return self._client is not None and not self._client.is_closed
