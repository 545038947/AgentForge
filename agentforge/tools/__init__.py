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
from agentforge.tools.checkpoint import (
    CheckpointManager,
    DEFAULT_EXCLUDES,
)
from agentforge.tools.toolsets import (
    ToolsetDefinition,
    ToolsetRegistry,
    register_toolset,
    get_toolset,
    resolve_toolset,
    BUILTIN_TOOLSETS,
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
    # checkpoint
    "CheckpointManager",
    "DEFAULT_EXCLUDES",
    # toolsets
    "ToolsetDefinition",
    "ToolsetRegistry",
    "register_toolset",
    "get_toolset",
    "resolve_toolset",
    "BUILTIN_TOOLSETS",
]
