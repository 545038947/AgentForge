"""Moonshot (Kimi) Provider 实现。

支持 Moonshot API（兼容 OpenAI 格式）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.client_factory import create_moonshot_client
from agentforge.providers.transports import ChatCompletionsTransport
from agentforge.types import NormalizedResponse, Usage
from agentforge.types.errors import ProviderError, ProviderRateLimitError
from agentforge.utils.schema_sanitizer import sanitize_moonshot_tools

logger = logging.getLogger(__name__)


class MoonshotProvider(Provider):
    """Moonshot (Kimi) Provider。

    支持：
    - OpenAI 兼容 API
    - 流式响应
    - 长上下文（最高 128K）

    使用示例：
        provider = MoonshotProvider(
            api_key="sk-...",
            model="moonshot-v1-8k",
        )

        response = provider.complete(messages)
    """

    name = "moonshot"

    # Moonshot 模型列表
    MODELS = {
        "moonshot-v1-8k": {"context_length": 8192},
        "moonshot-v1-32k": {"context_length": 32768},
        "moonshot-v1-128k": {"context_length": 131072},
    }

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "moonshot-v1-8k",
        timeout: float = 300.0,
        **kwargs,
    ):
        """初始化 Moonshot Provider。

        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选）
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
            supports_vision=False,
            supports_caching=False,
            supports_reasoning=False,
        )

    def _default_transport(self) -> ChatCompletionsTransport:
        """默认 Transport（使用 OpenAI 兼容格式）。"""
        return ChatCompletionsTransport()

    def _create_client(self) -> Any:
        """创建 API 客户端。"""
        return create_moonshot_client(
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
            tools: 工具定义（需要 Moonshot 特定清理）
            **kwargs: 其他参数

        Yields:
            原生响应块
        """
        if self._client is None:
            # SDK 未安装或 API 密钥未配置，抛出异常而非静默降级
            raise ProviderError(
                "Moonshot SDK 未安装或 API 密钥未配置，无法调用 API。"
                "请安装 openai 包（pip install openai）并配置有效的 API 密钥。",
                provider=self.name,
            )

        try:
            # 构建请求参数
            request_params = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "stream": True,
            }

            # Moonshot 特定工具 schema 清理
            if tools:
                sanitized_tools = sanitize_moonshot_tools(tools)
                request_params["tools"] = sanitized_tools

            # 添加其他参数
            for key in ["max_tokens", "temperature", "top_p"]:
                if key in kwargs:
                    request_params[key] = kwargs[key]

            # 执行流式调用
            stream = self._client.chat.completions.create(**request_params)

            for chunk in stream:
                yield chunk

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str or "429" in error_str:
                raise ProviderRateLimitError(
                    f"Moonshot 速率限制: {e}",
                    provider=self.name,
                ) from e
            else:
                raise ProviderError(
                    f"Moonshot API 调用失败: {e}",
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
            tools: 工具列表（Moonshot 支持，但需要 schema 清理）
            **kwargs: 其他参数

        Yields:
            响应块
        """
        # 转换消息
        converted_messages = self.transport.convert_messages(messages)

        # 转换工具（Moonshot 支持，但需要特定清理）
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
            tools: 工具列表（Moonshot 支持，但需要 schema 清理）
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
