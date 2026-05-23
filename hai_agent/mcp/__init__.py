"""MCP (Model Context Protocol) 支持。"""

from hai_agent.mcp.types import (
    MCPToolSchema,
    MCPResourceSchema,
    MCPToolResult,
    MCPResourceContent,
)
from hai_agent.mcp.errors import (
    MCPError,
    MCPConnectionError,
    MCPToolCallError,
    MCPResourceError,
    MCPConfigError,
)
from hai_agent.mcp.config import MCPConfig, MCPServerConfig
from hai_agent.mcp.client import MCPClient
from hai_agent.mcp.tool import MCPTool
from hai_agent.mcp.manager import MCPManager

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
