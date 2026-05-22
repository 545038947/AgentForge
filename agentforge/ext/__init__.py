"""框架开发者 API。

提供扩展 AgentForge 所需的接口，包括：
- Provider 扩展：自定义 Provider 和 Transport
- Tool 扩展：自定义工具和审批回调
- Memory 扩展：自定义记忆存储
- Skill 扩展：自定义技能
- 事件扩展：自定义事件类型和发射器
"""

# Provider 扩展
from agentforge.providers import (
    Provider,
    ProviderCapabilities,
)
from agentforge.providers.registry import (
    register_provider,
    get_provider,
    list_providers,
    ProviderRegistry,
)

# Transport 扩展
from agentforge.providers.transports import (
    Transport,
    ChatCompletionsTransport,
    AnthropicTransport,
)

# Tool 扩展
from agentforge.tools import (
    Tool,
    FunctionTool,
    ApprovalCallback,
    ApprovalDecision,
)

# Memory 扩展
from agentforge.memory import (
    MemoryProvider,
    MemoryBlock,
)

# Skill 扩展
from agentforge.skills import (
    Skill,
    SkillMetadata,
    FunctionSkill,
    register_skill,
    get_skill,
    list_skills,
)

# 事件扩展
from agentforge.events import (
    EventEmitter,
    EventType,
    Event,
)

__all__ = [
    # Provider 扩展
    "Provider",
    "ProviderCapabilities",
    "register_provider",
    "get_provider",
    "list_providers",
    "ProviderRegistry",
    # Transport 扩展
    "Transport",
    "ChatCompletionsTransport",
    "AnthropicTransport",
    # Tool 扩展
    "Tool",
    "FunctionTool",
    "ApprovalCallback",
    "ApprovalDecision",
    # Memory 扩展
    "MemoryProvider",
    "MemoryBlock",
    # Skill 扩展
    "Skill",
    "SkillMetadata",
    "FunctionSkill",
    "register_skill",
    "get_skill",
    "list_skills",
    # 事件扩展
    "EventEmitter",
    "EventType",
    "Event",
]
