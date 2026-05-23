"""MCP (Model Context Protocol) 支持。"""

from agentforge.mcp.types import (
    MCPToolSchema,
    MCPResourceSchema,
    MCPToolResult,
    MCPResourceContent,
)
from agentforge.mcp.errors import (
    MCPError,
    MCPConnectionError,
    MCPToolCallError,
    MCPResourceError,
    MCPConfigError,
)
from agentforge.mcp.config import MCPConfig, MCPServerConfig
from agentforge.mcp.client import MCPClient
from agentforge.mcp.tool import MCPTool
from agentforge.mcp.manager import MCPManager

__all__ = [
    # Types
    "MCPToolSchema",
    "MCPResourceSchema",
    "MCPToolResult",
    "MCPResourceContent",
    # Errors
    "MCPError",
    "MCPConnectionError",
    "MCPToolCallError",
    "MCPResourceError",
    "MCPConfigError",
    # Config
    "MCPConfig",
    "MCPServerConfig",
    # Client
    "MCPClient",
    "MCPTool",
    "MCPManager",
]
