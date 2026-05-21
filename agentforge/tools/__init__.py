"""工具系统模块。"""

from agentforge.tools.base import (
    Tool,
    FunctionTool,
    tool,
    ToolRegistry,
    register_tool,
    get_tool,
    list_tools,
)
from agentforge.tools.executor import (
    ToolExecutor,
    ToolExecution,
)
from agentforge.tools.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalCallback,
    ApprovalManager,
)

__all__ = [
    # base
    "Tool",
    "FunctionTool",
    "tool",
    "ToolRegistry",
    "register_tool",
    "get_tool",
    "list_tools",
    # executor
    "ToolExecutor",
    "ToolExecution",
    # approval
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalCallback",
    "ApprovalManager",
]
