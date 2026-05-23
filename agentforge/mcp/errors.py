"""MCP 错误类型。"""

from agentforge.types.errors import AgentForgeError


class MCPError(AgentForgeError):
    """MCP 相关错误基类。"""
    pass


class MCPConnectionError(MCPError):
    """MCP Server 连接失败。"""
    pass


class MCPToolCallError(MCPError):
    """MCP 工具调用失败。"""
    pass


class MCPResourceError(MCPError):
    """MCP Resource 访问失败。"""
    pass


class MCPConfigError(MCPError):
    """MCP 配置错误。"""
    pass