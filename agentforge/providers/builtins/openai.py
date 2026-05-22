"""OpenAI Provider 实现。

支持 OpenAI chat_completions API。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.client_factory import create_openai_client
from agentforge.providers.transports import ChatCompletionsTransport
from agentforge.types import NormalizedResponse, ToolCall, Usage
from agentforge.types.errors import ProviderError, ProviderRateLimitError

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
        timeout: float = 300.0,
        **kwargs,
    ):
        """初始化 OpenAI Provider。

        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选，用于自定义端点）
            model: 模型名称
            timeout: 超时时间（秒）
            **kwargs: 其他参数
        """
        self._model = model
        self._timeout = timeout
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
        return create_openai_client(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
        )

    def _do_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """执行流式 API 调用。

        Args:
            messages: 消息列表
            tools: 工具定义
            **kwargs: 其他参数

        Yields:
            原生响应块
        """
        if self._client is None:
            # SDK 未安装或 API 密钥未配置，返回模拟响应
            logger.warning("OpenAI SDK 未安装或 API 密钥未配置，使用模拟响应")
            # 创建一个模拟的 SDK 响应对象
            from dataclasses import dataclass

            @dataclass
            class MockFunction:
                name: str = ""
                arguments: str = ""

            @dataclass
            class MockToolCall:
                id: str = ""
                function: MockFunction = None

                def __post_init__(self):
                    if self.function is None:
                        self.function = MockFunction()

            @dataclass
            class MockMessage:
                content: str = ""
                tool_calls: list = None

                def __post_init__(self):
                    if self.tool_calls is None:
                        self.tool_calls = []

            @dataclass
            class MockChoice:
                message: MockMessage
                finish_reason: str = "stop"

            @dataclass
            class MockUsage:
                prompt_tokens: int = 10
                completion_tokens: int = 20
                total_tokens: int = 30

            @dataclass
            class MockResponse:
                choices: list
                model: str
                usage: MockUsage = None

                def __post_init__(self):
                    if self.usage is None:
                        self.usage = MockUsage()

            yield MockResponse(
                choices=[MockChoice(message=MockMessage(content="这是一个模拟响应（SDK 未安装或密钥未配置）。"))],
                model=self._model,
            )
            return

        try:
            # 构建请求参数
            request_params = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "stream": True,
            }

            if tools:
                request_params["tools"] = tools

            # 添加其他参数
            for key in ["max_tokens", "temperature", "top_p", "frequency_penalty", "presence_penalty"]:
                if key in kwargs:
                    request_params[key] = kwargs[key]

            # 执行流式调用
            stream = self._client.chat.completions.create(**request_params)

            for chunk in stream:
                yield chunk

        except Exception as e:
            # 检查是否是速率限制错误
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str or "429" in error_str:
                raise ProviderRateLimitError(
                    f"OpenAI 速率限制: {e}",
                    provider=self.name,
                ) from e
            else:
                raise ProviderError(
                    f"OpenAI API 调用失败: {e}",
                    provider=self.name,
                ) from e

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
        # 转换消息
        converted_messages = self.transport.convert_messages(messages)

        # 转换工具
        converted_tools = None
        if tools and self.capabilities.supports_tools:
            converted_tools = self.transport.convert_tools(tools)

        # 执行流式调用
        for raw_response in self._do_stream(
            messages=converted_messages,
            tools=converted_tools,
            model=kwargs.get("model", self._model),
            **kwargs,
        ):
            yield self.transport.normalize_response(raw_response)

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