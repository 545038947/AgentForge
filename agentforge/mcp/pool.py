"""MCP 连接池 — 复用已建立的 MCP 客户端连接，避免每次调用启动新进程。"""

import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional

from agentforge.mcp.config import MCPServerConfig
from agentforge.mcp.client import MCPClient
from agentforge.mcp.errors import MCPConnectionError

logger = logging.getLogger(__name__)


class MCPConnectionPool:
    """管理 MCP 客户端连接的池化复用。

    在后台事件循环中保持连接活跃，避免每次调用创建新进程。
    线程安全：外部同步代码通过 run_coroutine_threadsafe 调度。
    """

    def __init__(
        self,
        max_idle_seconds: float = 300.0,
        max_connections: int = 10,
    ):
        self._max_idle_seconds = max_idle_seconds
        self._max_connections = max_connections
        self._clients: Dict[str, MCPClient] = {}
        self._last_used: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._started = False
        self._closed = False

    def start(self) -> None:
        """启动后台事件循环。"""
        with self._lock:
            if self._started:
                return
            self._loop_thread = threading.Thread(
                target=self._run_loop, daemon=True, name="mcp-pool"
            )
            self._loop_thread.start()
            while self._loop is None:
                time.sleep(0.01)
            self._started = True

    def _run_loop(self) -> None:
        """后台线程运行事件循环。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._idle_cleanup_loop())
        except Exception:
            logger.debug("MCP 连接池事件循环退出")
        finally:
            self._loop.close()

    async def _idle_cleanup_loop(self) -> None:
        """定期清理空闲连接。"""
        while not self._closed:
            await asyncio.sleep(60.0)
            if self._closed:
                break
            now = time.monotonic()
            to_remove = []
            for key, last in self._last_used.items():
                if now - last > self._max_idle_seconds:
                    to_remove.append(key)
            for key in to_remove:
                client = self._clients.pop(key, None)
                self._last_used.pop(key, None)
                if client and client.is_connected():
                    try:
                        await client.disconnect()
                        logger.debug(f"清理空闲 MCP 连接: {key}")
                    except Exception as e:
                        logger.warning(f"清理 MCP 连接失败: {key}: {e}")

    def get_or_create(self, config: MCPServerConfig) -> MCPClient:
        """获取或创建 MCP 客户端连接（同步接口）。"""
        if not self._started:
            self.start()
        pool_key = self._config_key(config)
        with self._lock:
            if pool_key in self._clients:
                client = self._clients[pool_key]
                if client.is_connected():
                    self._last_used[pool_key] = time.monotonic()
                    return client
                del self._clients[pool_key]
                self._last_used.pop(pool_key, None)
            if len(self._clients) >= self._max_connections:
                oldest_key = min(self._last_used, key=self._last_used.get)
                old_client = self._clients.pop(oldest_key, None)
                self._last_used.pop(oldest_key, None)
                if old_client and old_client.is_connected():
                    future = asyncio.run_coroutine_threadsafe(
                        old_client.disconnect(), self._loop
                    )
                    try:
                        future.result(timeout=10.0)
                    except Exception:
                        pass
        # 在后台循环中创建新连接
        client = MCPClient(config)
        future = asyncio.run_coroutine_threadsafe(
            client.connect(), self._loop
        )
        try:
            future.result(timeout=30.0)
        except Exception as e:
            raise MCPConnectionError(f"连接池创建连接失败: {e}") from e
        with self._lock:
            self._clients[pool_key] = client
            self._last_used[pool_key] = time.monotonic()
        return client

    def call_tool(
        self, config: MCPServerConfig, tool_name: str, arguments: dict
    ) -> str:
        """通过连接池调用 MCP 工具（同步接口）。"""
        client = self.get_or_create(config)
        future = asyncio.run_coroutine_threadsafe(
            client.call_tool(tool_name, arguments), self._loop
        )
        try:
            result = future.result(timeout=60.0)
            return result.content
        except MCPConnectionError:
            with self._lock:
                pool_key = self._config_key(config)
                self._clients.pop(pool_key, None)
                self._last_used.pop(pool_key, None)
            client = self.get_or_create(config)
            future = asyncio.run_coroutine_threadsafe(
                client.call_tool(tool_name, arguments), self._loop
            )
            result = future.result(timeout=60.0)
            return result.content

    def shutdown(self) -> None:
        """关闭所有连接并停止事件循环。"""
        if self._closed:
            return
        self._closed = True
        if self._loop and not self._loop.is_closed():
            async def _close_all():
                for key, client in list(self._clients.items()):
                    try:
                        if client.is_connected():
                            await client.disconnect()
                    except Exception:
                        pass
                self._clients.clear()
                self._last_used.clear()
            future = asyncio.run_coroutine_threadsafe(_close_all(), self._loop)
            try:
                future.result(timeout=10.0)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)

    @staticmethod
    def _config_key(config: MCPServerConfig) -> str:
        """根据配置生成池键。"""
        if config.command:
            return f"cmd:{config.name}:{config.command}:{','.join(config.args)}"
        if config.url:
            return f"http:{config.name}:{config.url}"
        return f"cfg:{config.name}"
