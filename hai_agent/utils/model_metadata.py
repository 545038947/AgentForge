"""Model Metadata - 模型能力查询和上下文长度管理。

提供模型元数据查询、上下文长度获取、Token 估算等功能。

参考 hermes-agent/agent/model_metadata.py。
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 模型上下文长度映射
# 格式: model_prefix -> context_length
_MODEL_CONTEXT_LENGTHS: Dict[str, int] = {
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4-": 8192,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-": 4096,
    # Anthropic
    "claude-3-5-sonnet": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-2": 100000,
    "claude-": 200000,
    # Moonshot
    "moonshot-v1-128k": 131072,
    "moonshot-v1-32k": 32768,
    "moonshot-v1-8k": 8192,
    "moonshot-": 8192,
    # Qwen
    "qwen-max-longcontext": 30720,
    "qwen-max": 8192,
    "qwen-plus": 32768,
    "qwen-turbo": 8192,
    "qwen-": 8192,
    # DeepSeek
    "deepseek-reasoner": 64000,
    "deepseek-chat": 64000,
    "deepseek-": 64000,
    # Gemini
    "gemini-1.5-pro": 1000000,
    "gemini-1.5-flash": 1000000,
    "gemini-1.0-pro": 32760,
    "gemini-": 32760,
    # Llama
    "llama-3.1-405b": 128000,
    "llama-3.1-70b": 128000,
    "llama-3.1-8b": 128000,
    "llama-3-": 8192,
    "llama-2-": 4096,
    # Mistral
    "mistral-large": 128000,
    "mistral-medium": 32000,
    "mistral-small": 32000,
    "mistral-7b": 32768,
    "mixtral-": 32768,
    # 默认
    "default": 8192,
}

# 模型能力映射
_MODEL_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    # OpenAI
    "gpt-4o": {"tools": True, "vision": True, "streaming": True},
    "gpt-4-turbo": {"tools": True, "vision": True, "streaming": True},
    "gpt-4-": {"tools": True, "vision": False, "streaming": True},
    "gpt-3.5-": {"tools": True, "vision": False, "streaming": True},
    # Anthropic
    "claude-3-": {"tools": True, "vision": True, "streaming": True, "caching": True},
    "claude-2": {"tools": True, "vision": False, "streaming": True},
    # Moonshot
    "moonshot-": {"tools": False, "vision": False, "streaming": True},
    # Qwen
    "qwen-": {"tools": True, "vision": True, "streaming": True},
    # DeepSeek
    "deepseek-reasoner": {"tools": True, "vision": False, "streaming": True, "reasoning": True},
    "deepseek-": {"tools": True, "vision": False, "streaming": True},
    # Gemini
    "gemini-": {"tools": True, "vision": True, "streaming": True},
    # 默认
    "default": {"tools": True, "vision": False, "streaming": True},
}


def get_model_context_length(model: str) -> int:
    """获取模型的上下文长度。

    Args:
        model: 模型名称

    Returns:
        上下文长度（Token 数）
    """
    model_lower = model.lower().strip()

    # 精确匹配
    if model_lower in _MODEL_CONTEXT_LENGTHS:
        return _MODEL_CONTEXT_LENGTHS[model_lower]

    # 前缀匹配
    for prefix, length in sorted(_MODEL_CONTEXT_LENGTHS.items(), key=lambda x: -len(x[0])):
        if model_lower.startswith(prefix):
            return length

    # 从模型名提取（如 "128k"）
    match = re.search(r"(\d+)k", model_lower)
    if match:
        return int(match.group(1)) * 1024

    # 默认值
    return _MODEL_CONTEXT_LENGTHS["default"]


def get_model_capabilities(model: str) -> Dict[str, bool]:
    """获取模型能力。

    Args:
        model: 模型名称

    Returns:
        能力字典
    """
    model_lower = model.lower().strip()

    # 精确匹配
    if model_lower in _MODEL_CAPABILITIES:
        return _MODEL_CAPABILITIES[model_lower]

    # 前缀匹配
    for prefix, caps in sorted(_MODEL_CAPABILITIES.items(), key=lambda x: -len(x[0])):
        if model_lower.startswith(prefix):
            return caps

    # 默认值
    return _MODEL_CAPABILITIES["default"]


def supports_tools(model: str) -> bool:
    """检查模型是否支持工具调用。"""
    return get_model_capabilities(model).get("tools", True)


def supports_vision(model: str) -> bool:
    """检查模型是否支持视觉。"""
    return get_model_capabilities(model).get("vision", False)


def supports_streaming(model: str) -> bool:
    """检查模型是否支持流式输出。"""
    return get_model_capabilities(model).get("streaming", True)


def supports_caching(model: str) -> bool:
    """检查模型是否支持提示缓存。"""
    return get_model_capabilities(model).get("caching", False)


def supports_reasoning(model: str) -> bool:
    """检查模型是否支持推理（thinking）。"""
    return get_model_capabilities(model).get("reasoning", False)


def estimate_tokens(text: str) -> int:
    """估算文本的 Token 数。

    使用简单的启发式方法：平均每 4 个字符约 1 个 Token。
    对于中文，平均每 2 个字符约 1 个 Token。

    Args:
        text: 输入文本

    Returns:
        估算的 Token 数
    """
    if not text:
        return 0

    # 统计中文字符
    chinese_chars = len(re.findall(r"[一-鿿]", text))
    # 统计其他字符
    other_chars = len(text) - chinese_chars

    # 中文：约 2 字符/Token，其他：约 4 字符/Token
    return chinese_chars // 2 + other_chars // 4 + 1


def estimate_messages_tokens(messages: List[Dict]) -> int:
    """估算消息列表的 Token 数。

    Args:
        messages: 消息列表

    Returns:
        估算的 Token 数
    """
    total = 0

    for msg in messages:
        # 角色开销
        total += 4  # "role: " + role name

        # 内容
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        total += estimate_tokens(block.get("text", ""))
                    elif block.get("type") == "image_url":
                        total += 85  # 图片约 85 Token 开销

        # 工具调用
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            total += estimate_tokens(func.get("name", ""))
            total += estimate_tokens(func.get("arguments", ""))

        # 名称字段
        if "name" in msg:
            total += estimate_tokens(msg["name"])

    # 消息格式开销
    total += 3 * len(messages)

    return total


def get_model_family(model: str) -> str:
    """获取模型家族。

    Args:
        model: 模型名称

    Returns:
        家族名称
    """
    model_lower = model.lower()

    if model_lower.startswith("gpt"):
        return "openai"
    if model_lower.startswith("claude"):
        return "anthropic"
    if model_lower.startswith("moonshot") or model_lower.startswith("kimi"):
        return "moonshot"
    if model_lower.startswith("qwen"):
        return "qwen"
    if model_lower.startswith("deepseek"):
        return "deepseek"
    if model_lower.startswith("gemini"):
        return "gemini"
    if model_lower.startswith("llama"):
        return "llama"
    if model_lower.startswith("mistral") or model_lower.startswith("mixtral"):
        return "mistral"

    return "unknown"


def is_reasoning_model(model: str) -> bool:
    """检查是否是推理模型。

    推理模型会输出 thinking/reasoning blocks。
    """
    model_lower = model.lower()

    # 已知的推理模型
    reasoning_patterns = [
        "deepseek-reasoner",
        "o1-",  # OpenAI o1
        "claude-3-5-sonnet",  # Claude 3.5 Sonnet 支持 thinking
    ]

    for pattern in reasoning_patterns:
        if pattern in model_lower:
            return True

    return False


def get_default_max_tokens(model: str) -> int:
    """获取模型的默认最大输出 Token 数。

    Args:
        model: 模型名称

    Returns:
        默认最大输出 Token 数
    """
    context_length = get_model_context_length(model)

    # 通常输出限制是上下文长度的 1/4 到 1/2
    if context_length >= 100000:
        return 4096
    elif context_length >= 32000:
        return 4096
    elif context_length >= 8192:
        return 2048
    else:
        return 1024


__all__ = [
    "get_model_context_length",
    "get_model_capabilities",
    "supports_tools",
    "supports_vision",
    "supports_streaming",
    "supports_caching",
    "supports_reasoning",
    "estimate_tokens",
    "estimate_messages_tokens",
    "get_model_family",
    "is_reasoning_model",
    "get_default_max_tokens",
]