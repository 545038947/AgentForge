"""OpenAI Provider 实现。

支持 OpenAI chat_completions API。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.transports import ChatCompletionsTransport
from agentforge.types import NormalizedResponse, ToolCall, Usage

logger = logging.getLogger(__name__)


class OpenAIProvider(Provider):
    """OpenAI Provider。

    支持：
    - chat_completions API
    - 流式响应
    - 工具调用
    - 函数调用

    使用示例：
        provider = OpenAIProvider(
            api_key="sk-...",
            model="gpt-4",
        )

        response = provider.complete(messages, tools=tools)
    """

    name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "gpt-4",
        **kwargs,
    ):
        """初始化 OpenAI Provider。

        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选，用于自定义端点）
            model: 模型名称
            **kwargs: 其他参数
        """
        self._model = model
        self._kwargs = kwargs
        super().__init__(api_key=api_key, base_url=base_url)

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Provider 能力。"""
        return ProviderCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_vision=True,
            supports_caching=False,
            supports_reasoning=False,
        )

    def _default_transport(self) -> ChatCompletionsTransport:
        """默认 Transport。"""
        return ChatCompletionsTransport()

    def _create_client(self) -> Any:
        """创建 API 客户端。"""
        # 返回 None 表示使用模拟实现
        # 实际实现需要使用 openai 库
        return None

    def _do_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """执行流式 API 调用。"""
        # 模拟实现
        yield {"content": "这是一个模拟响应。", "model": self._model}

    def stream(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        **kwargs,
    ) -> Iterator[NormalizedResponse]:
        """流式调用 API。

        Args:
            messages: 消息列表
            tools: 工具列表（可选）
            **kwargs: 其他参数

        Yields:
            响应块
        """
        # 模拟实现
        yield NormalizedResponse(
            content="这是一个模拟响应。",
            model=self._model,
            usage=Usage(prompt_tokens=10, completion_tokens=20),
        )

    def complete(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        **kwargs,
    ) -> NormalizedResponse:
        """非流式调用 API。

        Args:
            messages: 消息列表
            tools: 工具列表（可选）
            **kwargs: 其他参数

        Returns:
            完整响应
        """
        final_response = None
        for chunk in self.stream(messages, tools, **kwargs):
            final_response = chunk

        return final_response or NormalizedResponse(content="")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "model": self._model,
            "base_url": self._base_url,
            "capabilities": self.capabilities.to_dict(),
        }