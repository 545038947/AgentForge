"""MCP Transport 抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class MCPTransport(ABC):
    """MCP 传输层抽象基类。"""

    @abstractmethod
    async def connect(self) -> None:
        """建立连接。"""
        pass

    @abstractmethod
    async def request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送 JSON-RPC 请求并等待响应。"""
        pass

    @abstractmethod
    async def send_notification(self, method: str, params: Dict[str, Any] = None) -> None:
        """发送 JSON-RPC 通知（无需响应）。"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭连接。"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """检查是否已连接。"""
        pass
