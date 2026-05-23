"""Anthropic Provider 实现。

支持 Anthropic messages API。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from hai_agent.providers.base import Provider, ProviderCapabilities
from hai_agent.providers.client_factory import create_anthropic_client
from hai_agent.providers.transports import AnthropicTransport
from hai_agent.types import NormalizedResponse, Usage
from hai_agent.types.errors import ProviderError, ProviderRateLimitError

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
        timeout: float = 300.0,
        **kwargs,
    ):
        """初始化 Anthropic Provider。

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
        return create_anthropic_client(
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
            # SDK 未安装或 API 密钥未配置，抛出异常而非静默降级
            raise ProviderError(
                "Anthropic SDK 未安装或 API 密钥未配置，无法调用 API。"
                "请安装 anthropic 包（pip install anthropic）并配置有效的 API 密钥。",
                provider=self.name,
            )

        try:
            # 提取 system prompt
            system = kwargs.pop("system", None)

            # 构建请求参数
            request_params = {
                "model": kwargs.get("model", self._model),
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 16384),
            }

            if system:
                request_params["system"] = system

            if tools:
                request_params["tools"] = tools

            # 添加其他参数
            for key in ["temperature", "top_p", "top_k"]:
                if key in kwargs:
                    request_params[key] = kwargs[key]

            # 执行流式调用
            with self._client.messages.stream(**request_params) as stream:
                for event in stream:
                    yield event

        except (OSError, ConnectionError, RuntimeError) as e:
            # 检查是否是速率限制错误
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str or "429" in error_str:
                raise ProviderRateLimitError(
                    f"Anthropic 速率限制: {e}",
                    provider=self.name,
                ) from e
            else:
                raise ProviderError(
                    f"Anthropic API 调用失败: {e}",
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

        # 添加 system prompt
        if system:
            request_kwargs["system"] = system

        # 执行流式调用
        for raw_response in self._do_stream(
            messages=converted_messages,
            tools=converted_tools,
            **request_kwargs,
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