"""Transport 层模块。"""

from hai_agent.providers.transports.base import (
    Transport,
    register_transport,
    get_transport,
    list_transports,
)
from hai_agent.providers.transports.chat_completions import ChatCompletionsTransport
from hai_agent.providers.transports.anthropic import AnthropicTransport
from hai_agent.providers.transports.bedrock import BedrockTransport

__all__ = [
    "Transport",
    "register_transport",
    "get_transport",
    "list_transports",
    "ChatCompletionsTransport",
    "AnthropicTransport",
    "BedrockTransport",
]

# 自动注册
register_transport("chat_completions", ChatCompletionsTransport)
register_transport("anthropic_messages", AnthropicTransport)
register_transport("bedrock_converse", BedrockTransport)