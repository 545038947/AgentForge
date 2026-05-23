"""模型能力系统。

提供 Provider 声明和查询模型特性的机制。
参考 hermes-agent/agent/model_metadata.py 实现。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class ModelCapabilities:
    """模型能力描述。

    Provider 通过此结构声明其支持的模型特性，
    用于运行时决策（如是否启用特定功能）。

    Attributes:
        context_length: 上下文窗口大小
        max_output_tokens: 最大输出 Token
        supports_tools: 是否支持工具调用
        supports_vision: 是否支持视觉
        supports_streaming: 是否支持流式
        supports_reasoning: 是否支持推理
        reasoning_effort_levels: 推理级别列表
        supports_prompt_caching: 是否支持提示缓存
        supports_parallel_tool_calls: 是否支持并行工具调用
        pricing: 价格信息
    """

    context_length: int = 128000
    max_output_tokens: int = 4096

    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True

    supports_reasoning: bool = False
    reasoning_effort_levels: List[str] = field(default_factory=list)

    supports_prompt_caching: bool = False
    supports_parallel_tool_calls: bool = True

    pricing: Optional[Dict[str, float]] = None


class ModelMetadataProvider:
    """模型元数据提供者接口。"""

    def get_model_capabilities(self, model: str) -> ModelCapabilities:
        """获取模型能力描述。

        Args:
            model: 模型名称

        Returns:
            模型能力
        """
        raise NotImplementedError

    def estimate_tokens(self, content: Union[str, List[Dict]]) -> int:
        """估算内容的 Token 数量。

        Args:
            content: 文本或多模态内容

        Returns:
            Token 数量估算
        """
        raise NotImplementedError


class DefaultModelMetadataProvider(ModelMetadataProvider):
    """默认模型元数据提供者。

    参考 hermes-agent/agent/model_metadata.py 实现。
    """

    # Token 估算常量
    CHARS_PER_TOKEN = 4  # 平均每 Token 约 4 字符
    IMAGE_TOKEN_ESTIMATE = 1600  # 单张图片约 1600 Token

    # 预定义模型能力
    MODEL_CAPABILITIES: Dict[str, ModelCapabilities] = {
        # OpenAI
        "gpt-4": ModelCapabilities(
            context_length=128000,
            supports_tools=True,
            supports_vision=True,
            supports_parallel_tool_calls=True,
        ),
        "gpt-4-turbo": ModelCapabilities(
            context_length=128000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),
        "gpt-4o": ModelCapabilities(
            context_length=128000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),

        # Anthropic
        "claude-opus-4": ModelCapabilities(
            context_length=200000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),
        "claude-sonnet-4": ModelCapabilities(
            context_length=200000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),

        # 中国大模型
        "deepseek-v3": ModelCapabilities(
            context_length=64000,
            supports_tools=True,
            supports_reasoning=True,
        ),
        "qwen-max": ModelCapabilities(
            context_length=32000,
            supports_tools=True,
            supports_vision=True,
        ),
        "kimi": ModelCapabilities(
            context_length=200000,
            supports_tools=True,
            supports_reasoning=True,
            reasoning_effort_levels=["low", "medium", "high"],
        ),
    }

    def get_model_capabilities(self, model: str) -> ModelCapabilities:
        """获取模型能力描述。

        Args:
            model: 模型名称

        Returns:
            模型能力
        """
        # 精确匹配
        if model in self.MODEL_CAPABILITIES:
            return self.MODEL_CAPABILITIES[model]

        # 模糊匹配（前缀）
        model_lower = model.lower()
        for key, caps in self.MODEL_CAPABILITIES.items():
            if model_lower.startswith(key.lower()):
                return caps

        # 默认值
        return ModelCapabilities()

    def estimate_tokens(self, content: Union[str, List[Dict]]) -> int:
        """估算内容的 Token 数量。

        Args:
            content: 文本或多模态内容

        Returns:
            Token 数量估算
        """
        if isinstance(content, str):
            return (len(content) + self.CHARS_PER_TOKEN - 1) // self.CHARS_PER_TOKEN

        total = 0
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    total += len(text) // self.CHARS_PER_TOKEN
                elif block_type == "image_url":
                    total += self.IMAGE_TOKEN_ESTIMATE
                elif block_type == "tool_use":
                    input_data = block.get("input", {})
                    total += len(json.dumps(input_data)) // self.CHARS_PER_TOKEN
                elif block_type == "tool_result":
                    content_str = block.get("content", "")
                    total += len(str(content_str)) // self.CHARS_PER_TOKEN

        return total


__all__ = [
    "ModelCapabilities",
    "ModelMetadataProvider",
    "DefaultModelMetadataProvider",
]