"""DeepSeek Provider 实现。

支持 DeepSeek API（兼容 OpenAI 格式）。

DeepSeek 特性：
- deepseek-chat: 通用对话模型
- deepseek-reasoner: 推理模型，返回 reasoning_content

参考 hermes-agent/plugins/model-providers/deepseek/__init__.py。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from hai_agent.providers.base import Provider, ProviderCapabilities
from hai_agent.providers.client_factory import create_deepseek_client
from hai_agent.providers.transports import ChatCompletionsTransport
from hai_agent.types import NormalizedResponse, Usage
from hai_agent.types.errors import ProviderError, ProviderRateLimitError

logger = logging.getLogger(__name__)


class DeepSeekProvider(Provider):
    """DeepSeek Provider。

    支持：
    - OpenAI 兼容 API
    - 流式响应
    - 工具调用
    - 推理能力（DeepSeek-Reasoner）

    使用示例：
        provider = DeepSeekProvider(
            api_key="sk-...",
            model="deepseek-chat",
        )

        response = provider.complete(messages, tools=tools)
    """

    name = "deepseek"

    # DeepSeek 模型列表
    MODELS = {
        "deepseek-chat": {"context_length": 64000, "supports_reasoning": False},
        "deepseek-reasoner": {"context_length": 64000, "supports_reasoning": True},
    }

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        timeout: float = 300.0,
        **kwargs,
    ):
        """初始化 DeepSeek Provider。

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
        # 检查是否是推理模型
        model_info = self.MODELS.get(self._model, {})
        supports_reasoning = model_info.get("supports_reasoning", False)

        return ProviderCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_vision=False,
            supports_caching=False,
            supports_reasoning=supports_reasoning,
        )

    @property
    def model(self) -> str:
        """当前模型名称。"""
        return self._model

    def _default_transport(self) -> ChatCompletionsTransport:
        """默认 Transport（使用 OpenAI 兼容格式）。"""
        return ChatCompletionsTransport()

    def _create_client(self) -> Any:
        """创建 API 客户端。"""
        return create_deepseek_client(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
        )

    def _is_reasoner_model(self) -> bool:
        """检查是否为推理模型。"""
        return self._model == "deepseek-reasoner"

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
                "DeepSeek SDK 未安装或 API 密钥未配置，无法调用 API。"
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

            if tools:
                request_params["tools"] = tools

            # 添加其他参数
            for key in ["max_tokens", "temperature", "top_p", "frequency_penalty", "presence_penalty"]:
                if key in kwargs:
                    request_params[key] = kwargs[key]

            # DeepSeek-Reasoner 特定参数
            if self._is_reasoner_model():
                # 推理模型可以配置推理努力程度
                reasoning_effort = kwargs.get("reasoning_effort")
                if reasoning_effort:
                    # DeepSeek 使用 extra_body 传递推理配置
                    extra_body = request_params.setdefault("extra_body", {})
                    extra_body["reasoning_effort"] = reasoning_effort

            # 执行流式调用
            stream = self._client.chat.completions.create(**request_params)

            for chunk in stream:
                yield chunk

        except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str or "429" in error_str:
                raise ProviderRateLimitError(
                    f"DeepSeek 速率限制: {e}",
                    provider=self.name,
                ) from e
            else:
                raise ProviderError(
                    f"DeepSeek API 调用失败: {e}",
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
            normalized = self.transport.normalize_response(raw_response)

            # DeepSeek-Reasoner: 提取 reasoning_content
            if self._is_reasoner_model() and normalized.provider_data:
                reasoning_content = normalized.provider_data.get("reasoning_content")
                if reasoning_content:
                    # 将 reasoning_content 合并到 reasoning 字段
                    normalized = NormalizedResponse(
                        content=normalized.content,
                        tool_calls=normalized.tool_calls,
                        finish_reason=normalized.finish_reason,
                        reasoning=reasoning_content,
                        usage=normalized.usage,
                        provider_data=normalized.provider_data,
                    )

            yield normalized

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
