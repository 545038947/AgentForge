"""MCP Client - 与 MCP Server 交互的核心客户端。"""

from typing import Any, Dict, List, Optional

from agentforge.mcp.config import MCPServerConfig
from agentforge.mcp.errors import MCPConnectionError, MCPToolCallError, MCPResourceError
from agentforge.mcp.types import (
    MCPToolSchema,
    MCPResourceSchema,
    MCPToolResult,
    MCPResourceContent,
)
from agentforge.mcp.transports import StdioTransport, HTTPTransport
from agentforge.mcp.transport import MCPTransport


class MCPClient:
    """MCP Server 客户端，负责连接、工具调用和资源访问。"""

    def __init__(self, config: MCPServerConfig):
        """
        初始化 MCP Client。

        Args:
            config: MCP Server 配置
        """
        self.config = config
        self.name = config.name
        self._transport: Optional[MCPTransport] = None
        self._tools: List[MCPToolSchema] = []
        self._resources: List[MCPResourceSchema] = []
        self._initialized = False

    async def connect(self) -> None:
        """连接到 MCP Server 并初始化。"""
        if self._initialized:
            return

        # 根据配置创建 Transport
        if self.config.transport == "stdio":
            self._transport = StdioTransport(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env,
            )
        elif self.config.transport == "http":
            self._transport = HTTPTransport(
                url=self.config.url,
                api_key=self.config.api_key,
                headers=self.config.headers,
            )
        else:
            raise MCPConnectionError(f"Unknown transport: {self.config.transport}")

        # 建立连接
        await self._transport.connect()

        # 发送初始化请求
        await self._initialize()

        # 获取工具和资源列表
        await self._load_capabilities()

        self._initialized = True

    async def _initialize(self) -> None:
        """发送 MCP 初始化协议。"""
        # MCP 初始化握手
        result = await self._transport.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                },
                "clientInfo": {
                    "name": "agentforge",
                    "version": "1.0.0",
                },
            },
        )

        # 发送 initialized 通知（无响应）
        await self._transport.send_notification("notifications/initialized", {})

    async def _load_capabilities(self) -> None:
        """加载 Server 提供的工具和资源。"""
        # 获取工具列表
        try:
            tools_result = await self._transport.request("tools/list", {})
            self._tools = [
                MCPToolSchema.from_dict(tool)
                for tool in tools_result.get("tools", [])
            ]
        except MCPConnectionError:
            # Server 可能不支持 tools
            self._tools = []

        # 获取资源列表
        try:
            resources_result = await self._transport.request("resources/list", {})
            self._resources = [
                MCPResourceSchema.from_dict(res)
                for res in resources_result.get("resources", [])
            ]
        except MCPConnectionError:
            # Server 可能不支持 resources
            self._resources = []

    async def disconnect(self) -> None:
        """断开与 MCP Server 的连接。"""
        if self._transport:
            await self._transport.close()
            self._transport = None
        self._initialized = False

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any] = None
    ) -> MCPToolResult:
        """
        调用 MCP 工具。

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具调用结果
        """
        if not self.is_connected():
            raise MCPConnectionError("Not connected to MCP Server")

        try:
            result = await self._transport.request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            )
            return MCPToolResult.from_dict(result)
        except MCPConnectionError as e:
            raise MCPToolCallError(f"Tool call failed: {e}") from e

    async def read_resource(self, uri: str) -> MCPResourceContent:
        """
        读取 MCP 资源。

        Args:
            uri: 资源 URI

        Returns:
            资源内容
        """
        if not self.is_connected():
            raise MCPConnectionError("Not connected to MCP Server")

        try:
            result = await self._transport.request(
                "resources/read",
                {"uri": uri},
            )
            return MCPResourceContent.from_dict(result)
        except MCPConnectionError as e:
            raise MCPResourceError(f"Resource read failed: {e}") from e

    def get_tools(self) -> List[MCPToolSchema]:
        """获取 Server 提供的所有工具 Schema。"""
        return self._tools

    def get_resources(self) -> List[MCPResourceSchema]:
        """获取 Server 提供的所有资源 Schema。"""
        return self._resources

    def is_connected(self) -> bool:
        """检查是否已连接。"""
        return self._transport is not None and self._transport.is_connected()

    def get_tool_schema(self, tool_name: str) -> Optional[MCPToolSchema]:
        """获取指定工具的 Schema。"""
        for tool in self._tools:
            if tool.name == tool_name:
                return tool
        return None