"""MCP Manager - 管理多个 MCP Server 连接和工具注册。"""

from typing import Any, Dict, List, Optional

from agentforge.mcp.config import MCPConfig, MCPServerConfig
from agentforge.mcp.client import MCPClient
from agentforge.mcp.tool import MCPTool
from agentforge.mcp.errors import MCPConfigError, MCPConnectionError


class MCPManager:
    """MCP Server 管理器，负责连接管理、工具注册和资源管理。"""

    def __init__(self):
        """初始化 MCP Manager。"""
        self._clients: Dict[str, MCPClient] = {}
        self._tools: Dict[str, MCPTool] = {}
        self._initialized = False

    async def initialize(self, config: MCPConfig) -> None:
        """
        从配置初始化所有 MCP Server。

        Args:
            config: MCP 配置
        """
        for server_config in config.servers:
            if not server_config.enabled:
                continue

            try:
                client = MCPClient(server_config)
                await client.connect()

                self._clients[server_config.name] = client

                # 注册所有工具
                for tool_schema in client.get_tools():
                    tool = MCPTool(client, tool_schema)
                    # 使用 server_name.tool_name 格式避免冲突
                    full_name = f"{server_config.name}.{tool_schema.name}"
                    self._tools[full_name] = tool

            except MCPConnectionError as e:
                # 记录错误但继续初始化其他 Server
                print(f"Failed to connect to MCP Server {server_config.name}: {e}")

        self._initialized = True

    async def initialize_from_yaml(self, config_path: str) -> None:
        """
        从 YAML 配置文件初始化。

        Args:
            config_path: YAML 配置文件路径
        """
        config = MCPConfig.from_yaml(config_path)
        await self.initialize(config)

    async def initialize_from_dict(self, config_data: dict) -> None:
        """
        从字典配置初始化。

        Args:
            config_data: 配置字典
        """
        config = MCPConfig.from_dict(config_data)
        await self.initialize(config)

    async def shutdown(self) -> None:
        """关闭所有 MCP Server 连接。"""
        for client in self._clients.values():
            try:
                await client.disconnect()
            except Exception:
                pass

        self._clients.clear()
        self._tools.clear()
        self._initialized = False

    def get_all_tools(self) -> List[MCPTool]:
        """获取所有已注册的 MCP 工具。"""
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """
        获取指定名称的工具。

        Args:
            tool_name: 工具名称（可以是短名或完整名）

        Returns:
            MCPTool 实例，如果不存在则返回 None
        """
        # 先尝试完整名称
        if tool_name in self._tools:
            return self._tools[tool_name]

        # 尝试短名（遍历所有 server）
        for full_name, tool in self._tools.items():
            if full_name.endswith(f".{tool_name}"):
                return tool

        return None

    def get_client(self, server_name: str) -> Optional[MCPClient]:
        """获取指定 Server 的客户端。"""
        return self._clients.get(server_name)

    def get_server_names(self) -> List[str]:
        """获取所有已连接的 Server 名称。"""
        return list(self._clients.keys())

    def get_tools_for_server(self, server_name: str) -> List[MCPTool]:
        """获取指定 Server 的所有工具。"""
        return [
            tool
            for name, tool in self._tools.items()
            if name.startswith(f"{server_name}.")
        ]

    def is_initialized(self) -> bool:
        """检查是否已初始化。"""
        return self._initialized

    def is_server_connected(self, server_name: str) -> bool:
        """检查指定 Server 是否已连接。"""
        client = self._clients.get(server_name)
        return client is not None and client.is_connected()

    async def call_tool(self, tool_name: str, arguments: dict = None) -> str:
        """
        调用 MCP 工具。

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        tool = self.get_tool(tool_name)
        if tool is None:
            raise MCPConfigError(f"Tool not found: {tool_name}")

        # 直接使用 client 调用工具
        result = await tool._client.call_tool(tool.name, arguments or {})
        return result.content

    async def read_resource(self, server_name: str, uri: str) -> str:
        """
        读取 MCP 资源。

        Args:
            server_name: Server 名称
            uri: 资源 URI

        Returns:
            资源内容
        """
        client = self.get_client(server_name)
        if client is None:
            raise MCPConfigError(f"Server not found: {server_name}")

        content = await client.read_resource(uri)
        return content.text

    def get_tool_schemas_for_llm(self) -> List[Dict[str, Any]]:
        """获取所有工具的 Schema（用于 LLM 调用）。"""
        return [tool.get_schema() for tool in self._tools.values()]