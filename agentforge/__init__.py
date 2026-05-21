"""
AgentForge - 可复用的 Agent 框架库

提供便捷的高层 API 用于构建 Agent 应用，同时支持框架开发者扩展组件。
"""

__version__ = "0.1.0"

# 核心类型
from agentforge.types import (
    Message,
    ContentBlock,
    TextContent,
    ImageContent,
    ToolUseContent,
    ToolResultContent,
    NormalizedResponse,
    ToolCall,
    Usage,
    ToolSpec,
    ToolResult,
)

# 错误类型
from agentforge.types.errors import (
    AgentForgeError,
    ConfigurationError,
    ProviderError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ToolError,
    ToolExecutionError,
    ToolApprovalDeniedError,
    ToolTimeoutError,
    DelegationError,
    DelegationDepthExceededError,
    ContextError,
    ContextCompressionError,
    InterruptException,
)

# 配置
from agentforge.config import Settings

# 便捷函数（将在 agent.py 实现后添加）
# from agentforge.agent import Agent, create_agent, quick_chat

__all__ = [
    # 版本
    "__version__",
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
    # 工具类型
    "ToolSpec",
    "ToolResult",
    # 错误类型
    "AgentForgeError",
    "ConfigurationError",
    "ProviderError",
    "ProviderConnectionError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ToolError",
    "ToolExecutionError",
    "ToolApprovalDeniedError",
    "ToolTimeoutError",
    "DelegationError",
    "DelegationDepthExceededError",
    "ContextError",
    "ContextCompressionError",
    "InterruptException",
    # 配置
    "Settings",
]
