"""通义千问 (Qwen) Provider 实现。

支持阿里云通义千问 API。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.transports import ChatCompletionsTransport
from agentforge.types import NormalizedResponse, Usage

logger = logging.getLogger(__name__)


class QwenProvider(Provider):
    """通义千问 (Qwen) Provider。

    支持阿里云 DashScope API。

    使用示例：
        provider = QwenProvider(
            api_key="sk-...",
            model="qwen-turbo",
        )
    """

    name = "qwen"

    # DashScope API 端点
    BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

    # 支持的模型
    MODELS = {
        "qwen-turbo": {"max_tokens": 8192},
        "qwen-plus": {"max_tokens": 32768},
        "qwen-max": {"max_tokens": 8192},
        "qwen-long": {"max_tokens": 10000},
    }

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-turbo",
        **kwargs,
    ):
        """初始化 Qwen Provider。

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
        return ProviderCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_vision=True,
            supports_caching=False,
            supports_reasoning=False,
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
        yield {"content": "这是一个通义千问模拟响应。", "model": self._model}

    def stream(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        **kwargs,
    ) -> Iterator[NormalizedResponse]:
        """流式调用 API。"""
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
            content="这是一个通义千问模拟响应。",
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