"""Anthropic Provider 实现。

支持 Anthropic messages API。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.transports import AnthropicTransport
from agentforge.types import NormalizedResponse, Usage

logger = logging.getLogger(__name__)


class AnthropicProvider(Provider):
    """Anthropic Provider。

    支持：
    - messages API
    - 流式响应
    - 工具调用
    - 视觉能力
    - Prompt Caching
    - Extended Thinking

    使用示例：
        provider = AnthropicProvider(
            api_key="sk-ant-...",
            model="claude-3-opus",
        )

        response = provider.complete(messages, tools=tools)
    """

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "claude-3-opus-20240229",
        **kwargs,
    ):
        """初始化 Anthropic Provider。

        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选）
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
            supports_caching=True,
            supports_reasoning=True,  # Anthropic 支持 extended thinking
        )

    def supports(self, capability: str) -> bool:
        """检查是否支持特定能力。

        Args:
            capability: 能力名称

        Returns:
            是否支持
        """
        return self.capabilities.supports(capability)

    def _default_transport(self) -> AnthropicTransport:
        """默认 Transport。"""
        return AnthropicTransport()

    def _create_client(self) -> Any:
        """创建 API 客户端。"""
        # 返回 None 表示使用模拟实现
        # 实际实现需要使用 anthropic 库
        return None

    def _do_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """执行流式 API 调用。"""
        # 模拟实现
        yield {"content": "这是一个 Anthropic 模拟响应。", "model": self._model}

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
        # 使用 Transport 转换消息
        system, converted_messages = self.transport.convert_messages(messages, **kwargs)

        # 转换工具格式
        converted_tools = None
        if tools:
            converted_tools = self.transport.convert_tools(tools)

        # 构建请求参数
        request_kwargs = self.transport.build_kwargs(
            model=self._model,
            messages=messages,
            tools=tools,
            max_tokens=kwargs.get("max_tokens", 16384),
            stream=True,
            **kwargs,
        )

        # 调用 API（模拟实现）
        yield self._mock_stream_response()

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

    def _mock_stream_response(self) -> NormalizedResponse:
        """模拟流式响应（用于测试）。"""
        return NormalizedResponse(
            content="这是一个 Anthropic 模拟响应。",
            model=self._model,
            usage=Usage(prompt_tokens=10, completion_tokens=20),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "model": self._model,
            "base_url": self._base_url,
            "capabilities": self.capabilities.to_dict(),
        }