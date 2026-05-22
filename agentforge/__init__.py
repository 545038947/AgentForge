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
    StreamDelta,
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
    classify_api_error,
    ErrorReason,
    ClassifiedError,
)

# 配置
from agentforge.config import Settings

# Agent
from agentforge.agent import Agent, quick_chat

# 工具
from agentforge.tools import (
    Tool,
    FunctionTool,
    tool,
)

# 事件
from agentforge.events import (
    EventType,
    Event,
    EventEmitter,
    EventDispatcher,
    on_event,
)

# 中断
from agentforge.interrupt import (
    InterruptToken,
    InterruptHandler,
)

# 记忆
from agentforge.memory import (
    MemoryProvider,
    InMemoryProvider,
    FileBasedProvider,
    MemoryBlock,
    MemoryManager,
    sanitize_context,
    StreamingContextScrubber,
)

# 技能
from agentforge.skills import (
    Skill,
    SkillMetadata,
    FunctionSkill,
    SkillRegistry,
    SkillLoader,
    SkillPackage,
    SkillHotReloader,
    register_skill,
    get_skill,
    list_skills,
    discover_and_load_skills,
)

# 核心功能
from agentforge.core import (
    IterationBudget,
    jittered_backoff,
    RetryPolicy,
    RetryContext,
    FallbackProvider,
    FallbackChain,
    ExecutionConfig,
    ExecutionState,
    ExecutionResult,
    ExecutionEngine,
    CredentialPool,
    PooledCredential,
    ModelCapabilities,
    DefaultModelMetadataProvider,
)

# 工具集
from agentforge.tools.toolsets import (
    ToolsetDefinition,
    ToolsetRegistry,
    register_toolset,
    get_toolset,
    resolve_toolset,
)

# 会话管理
from agentforge.session import (
    SessionProvider,
    SessionInfo,
    MessageRecord,
    InMemorySessionProvider,
)

# Profile 系统
from agentforge.profiles import (
    AgentProfile,
    ProviderCredentials,
    ProviderRegistry,
    ProfileRegistry,
)

# 触发内置 Provider 自动注册
import agentforge.providers.builtins

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
    "StreamDelta",
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
    "classify_api_error",
    "ErrorReason",
    "ClassifiedError",
    # 配置
    "Settings",
    # Agent
    "Agent",
    "quick_chat",
    # 工具
    "Tool",
    "FunctionTool",
    "tool",
    # 事件
    "EventType",
    "Event",
    "EventEmitter",
    "EventDispatcher",
    "on_event",
    # 中断
    "InterruptToken",
    "InterruptHandler",
    # 记忆
    "MemoryProvider",
    "InMemoryProvider",
    "FileBasedProvider",
    "MemoryBlock",
    "MemoryManager",
    "sanitize_context",
    "StreamingContextScrubber",
    # 技能
    "Skill",
    "SkillMetadata",
    "FunctionSkill",
    "SkillRegistry",
    "SkillLoader",
    "SkillPackage",
    "SkillHotReloader",
    "register_skill",
    "get_skill",
    "list_skills",
    "discover_and_load_skills",
    # 核心功能
    "IterationBudget",
    "jittered_backoff",
    "RetryPolicy",
    "RetryContext",
    "FallbackProvider",
    "FallbackChain",
    "ExecutionConfig",
    "ExecutionState",
    "ExecutionResult",
    "ExecutionEngine",
    "CredentialPool",
    "PooledCredential",
    # 模型能力
    "ModelCapabilities",
    "DefaultModelMetadataProvider",
    # 工具集
    "ToolsetDefinition",
    "ToolsetRegistry",
    "register_toolset",
    "get_toolset",
    "resolve_toolset",
    # 会话管理
    "SessionProvider",
    "SessionInfo",
    "MessageRecord",
    "InMemorySessionProvider",
    # Profile 系统
    "AgentProfile",
    "ProviderCredentials",
    "ProviderRegistry",
    "ProfileRegistry",
]
