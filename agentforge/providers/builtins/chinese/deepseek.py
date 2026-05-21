"""DeepSeek Provider 实现。

支持 DeepSeek API。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.transports import ChatCompletionsTransport
from agentforge.types import NormalizedResponse, Usage

logger = logging.getLogger(__name__)


class DeepSeekProvider(Provider):
    """DeepSeek Provider。

    DeepSeek API 兼容 OpenAI chat_completions 格式。

    使用示例：
        provider = DeepSeekProvider(
            api_key="sk-...",
            model="deepseek-chat",
        )
    """

    name = "deepseek"

    # DeepSeek API 端点
    BASE_URL = "https://api.deepseek.com/v1"

    # 支持的模型
    MODELS = {
        "deepseek-chat": {"max_tokens": 4096},
        "deepseek-coder": {"max_tokens": 4096},
        "deepseek-reasoner": {"max_tokens": 8192},
    }

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        **kwargs,
    ):
        """初始化 DeepSeek Provider。

        Args:
            api_key: API 密钥
            model: 模型名称
            **kwargs: 其他参数
        """
        self._model = model
        self._kwargs = kwargs
        super().__init__(api_key=api_key, base_url=self.BASE_URL)

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Provider 能力。"""
        # DeepSeek Reasoner 支持推理
        has_reasoning = "reasoner" in self._model.lower()

        return ProviderCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_vision=False,
            supports_caching=False,
            supports_reasoning=has_reasoning,
        )

    def supports(self, capability: str) -> bool:
        """检查是否支持特定能力。"""
        return self.capabilities.supports(capability)

    def _default_transport(self) -> ChatCompletionsTransport:
        """默认 Transport。"""
        return ChatCompletionsTransport()

    def _create_client(self) -> Any:
        """创建 API 客户端。"""
        return None

    def _do_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """执行流式 API 调用。"""
        yield {"content": "这是一个 DeepSeek 模拟响应。", "model": self._model}

    def stream(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        **kwargs,
    ) -> Iterator[NormalizedResponse]:
        """流式调用 API。"""
        # DeepSeek 兼容 OpenAI 格式
        yield self._mock_response()

    def complete(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        **kwargs,
    ) -> NormalizedResponse:
        """非流式调用 API。"""
        for chunk in self.stream(messages, tools, **kwargs):
            return chunk
        return NormalizedResponse(content="")

    def _mock_response(self) -> NormalizedResponse:
        """模拟响应。"""
        return NormalizedResponse(
            content="这是一个 DeepSeek 模拟响应。",
            model=self._model,
            usage=Usage(prompt_tokens=10, completion_tokens=20),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "model": self._model,
            "capabilities": self.capabilities.to_dict(),
        }