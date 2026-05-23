"""AgentForge 核心类型定义。"""

from hai_agent.types.messages import (
    Message,
    ContentBlock,
    TextContent,
    ImageContent,
    ToolUseContent,
    ToolResultContent,
)
from hai_agent.types.responses import (
    NormalizedResponse,
    ToolCall,
    Usage,
    StreamDelta,
)
from hai_agent.types.tools import (
    ToolSpec,
    ToolResult,
)
from hai_agent.types.errors import (
    ErrorReason,
    ClassifiedError,
    AgentForgeError,
    ConfigurationError,
    ProviderError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderContextOverflowError,
    ToolError,
    ToolExecutionError,
    ToolApprovalDeniedError,
    ToolTimeoutError,
    DelegationError,
    DelegationDepthExceededError,
    ContextError,
    ContextCompressionError,
    InterruptException,
    classify_api_error,
)

__all__ = [
    # 消息类型
    "Message",
    "ContentBlock",
    "TextContent",
    "ImageContent",
    "ToolUseContent",
    "ToolResultContent",
    # 响应类型
    "NormalizedResponse",
    "ToolCall",
    "Usage",
    "StreamDelta",
    # 工具类型
    "ToolSpec",
    "ToolResult",
    # 错误类型
    "ErrorReason",
    "ClassifiedError",
    "AgentForgeError",
    "ConfigurationError",
    "ProviderError",
    "ProviderConnectionError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderContextOverflowError",
    "ToolError",
    "ToolExecutionError",
    "ToolApprovalDeniedError",
    "ToolTimeoutError",
    "DelegationError",
    "DelegationDepthExceededError",
    "ContextError",
    "ContextCompressionError",
    "InterruptException",
    # 错误分类函数
    "classify_api_error",
]
