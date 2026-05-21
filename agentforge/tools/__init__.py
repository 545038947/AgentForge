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
from agentforge.tools.guardrails import (
    ToolCallGuardrailController,
    ToolCallGuardrailConfig,
    ToolCallSignature,
    ToolGuardrailDecision,
    classify_tool_failure,
    IDEMPOTENT_TOOL_NAMES,
    MUTATING_TOOL_NAMES,
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
    # guardrails
    "ToolCallGuardrailController",
    "ToolCallGuardrailConfig",
    "ToolCallSignature",
    "ToolGuardrailDecision",
    "classify_tool_failure",
    "IDEMPOTENT_TOOL_NAMES",
    "MUTATING_TOOL_NAMES",
]
