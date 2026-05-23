"""自定义 Provider 实现。

支持通过配置文件定义兼容 OpenAI/Anthropic/Ollama 三种 API 格式的自定义 Provider。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from hai_agent.providers.base import Provider, ProviderCapabilities
from hai_agent.providers.profile import ProviderProfile
from hai_agent.types import NormalizedResponse
from hai_agent.types.errors import ProviderError, ProviderConnectionError, ProviderRateLimitError

logger = logging.getLogger(__name__)


class CustomProvider(Provider):
    """自定义 Provider。

    根据配置动态创建 Provider，支持三种 API 模式：
    - chat_completions: OpenAI 兼容格式
    - anthropic_messages: Anthropic 格式
    - ollama: Ollama 格式（与 chat_completions 相同）

    使用示例：
        # 通过配置创建
        config = {
            "name": "openrouter",
            "api_mode": "chat_completions",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-xxx",
        }
        provider = CustomProvider.from_config(config)

        # 或直接创建
        provider = CustomProvider(
            name="my-provider",
            api_mode="chat_completions",
            base_url="http://localhost:8080/v1",
            api_key="my-key",
        )
    """

    def __init__(
        self,
        name: str,
        api_mode: str = "chat_completions",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "default",
        timeout: float = 300.0,
        default_headers: Optional[Dict[str, str]] = None,
        supports_tools: bool = True,
        supports_streaming: bool = True,
        supports_vision: bool = False,
        supports_caching: bool = False,
        supports_reasoning: bool = False,
        **kwargs,
    ):
        """初始化自定义 Provider。

        Args:
            name: Provider 名称
            api_mode: API 模式（chat_completions/anthropic_messages）
            api_key: API 密钥
            base_url: API 基础 URL
            model: 默认模型名称
            timeout: 请求超时时间
            default_headers: 默认请求头
            supports_tools: 是否支持工具调用
            supports_streaming: 是否支持流式响应
            supports_vision: 是否支持视觉
            supports_caching: 是否支持缓存
            supports_reasoning: 是否支持推理
            **kwargs: 其他参数
        """
        self._custom_name = name
        self._api_mode = api_mode
        self._model = model
        self._timeout = timeout
        self._default_headers = default_headers or {}
        self._kwargs = kwargs

        # 能力配置
        self._capabilities = ProviderCapabilities(
            supports_tools=supports_tools,
            supports_streaming=supports_streaming,
            supports_vision=supports_vision,
            supports_caching=supports_caching,
            supports_reasoning=supports_reasoning,
        )

        # 调用父类初始化
        super().__init__(api_key=api_key, base_url=base_url)

    @property
    def name(self) -> str:
        """Provider 名称。"""
        return self._custom_name

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Provider 能力。"""
        return self._capabilities

    def _default_transport(self) -> Any:
        """根据 api_mode 选择 Transport。"""
        from hai_agent.providers.transports import get_transport

        # 映射 api_mode 到 transport 名称
        transport_map = {
            "chat_completions": "chat_completions",
            "openai": "chat_completions",
            "ollama": "chat_completions",
            "anthropic_messages": "anthropic_messages",
            "anthropic": "anthropic_messages",
        }

        transport_name = transport_map.get(self._api_mode, "chat_completions")
        transport_class = get_transport(transport_name)

        if transport_class is None:
            logger.warning(
                f"未找到 Transport '{transport_name}'，使用默认 chat_completions"
            )
            from hai_agent.providers.transports import ChatCompletionsTransport
            transport_class = ChatCompletionsTransport

        return transport_class()

    def _create_client(self) -> Any:
        """创建 API 客户端。"""
        if self._api_mode in ("chat_completions", "openai", "ollama"):
            return self._create_openai_client()
        elif self._api_mode in ("anthropic_messages", "anthropic"):
            return self._create_anthropic_client()
        else:
            # 默认使用 OpenAI 客户端
            return self._create_openai_client()

    def _create_openai_client(self) -> Any:
        """创建 OpenAI 兼容客户端。"""
        try:
            from openai import OpenAI

            return OpenAI(
                api_key=self._api_key or "no-key",
                base_url=self._base_url,
                timeout=self._timeout,
                default_headers=self._default_headers or None,
            )
        except ImportError:
            logger.warning(
                "openai SDK 未安装，将使用 HTTP 直接调用。"
                "建议安装: pip install openai"
            )
            return None

    def _create_anthropic_client(self) -> Any:
        """创建 Anthropic 兼容客户端。"""
        try:
            from anthropic import Anthropic

            return Anthropic(
                api_key=self._api_key or "no-key",
                base_url=self._base_url,
                timeout=self._timeout,
                default_headers=self._default_headers or None,
            )
        except ImportError:
            logger.warning(
                "anthropic SDK 未安装，将使用 HTTP 直接调用。"
                "建议安装: pip install anthropic"
            )
            return None

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
        model = kwargs.get("model", self._model)

        if self._client is None:
            # SDK 未安装，使用 HTTP 直接调用
            yield from self._do_stream_http(messages, tools, model, **kwargs)
            return

        try:
            if self._api_mode in ("anthropic_messages", "anthropic"):
                yield from self._do_stream_anthropic(messages, tools, model, **kwargs)
            else:
                yield from self._do_stream_openai(messages, tools, model, **kwargs)

        except (OSError, ConnectionError, TimeoutError, RuntimeError) as e:
            error_str = str(e).lower()
            if "connection" in error_str or "refused" in error_str:
                raise ProviderConnectionError(
                    f"无法连接到 {self.name} ({self._base_url}): {e}",
                    provider=self.name,
                ) from e
            elif "rate" in error_str or "429" in error_str:
                raise ProviderRateLimitError(
                    f"{self.name} 速率限制: {e}",
                    provider=self.name,
                ) from e
            else:
                raise ProviderError(
                    f"{self.name} API 调用失败: {e}",
                    provider=self.name,
                ) from e

    def _do_stream_openai(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: str = None,
        **kwargs,
    ) -> Iterator[Any]:
        """OpenAI 兼容流式调用。"""
        request_params = {
            "model": model or self._model,
            "messages": messages,
            "stream": True,
        }

        if tools:
            request_params["tools"] = tools

        # 添加额外参数
        for key in ["max_tokens", "temperature", "top_p", "frequency_penalty", "presence_penalty"]:
            if key in kwargs:
                request_params[key] = kwargs[key]

        stream = self._client.chat.completions.create(**request_params)
        for chunk in stream:
            yield chunk

    def _do_stream_anthropic(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: str = None,
        **kwargs,
    ) -> Iterator[Any]:
        """Anthropic 兼容流式调用。"""
        # 分离系统消息
        system = None
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        request_params = {
            "model": model or self._model,
            "messages": filtered_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        if system:
            request_params["system"] = system
        if tools:
            request_params["tools"] = tools

        for key in ["temperature", "top_p"]:
            if key in kwargs:
                request_params[key] = kwargs[key]

        with self._client.messages.stream(**request_params) as stream:
            for event in stream:
                yield event

    def _do_stream_http(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: str = None,
        **kwargs,
    ) -> Iterator[Any]:
        """HTTP 直接调用（SDK 未安装时的 fallback）。"""
        import json
        import requests
        from dataclasses import dataclass

        endpoint = self._base_url.rstrip("/") + "/chat/completions"
        request_body = {
            "model": model or self._model,
            "messages": messages,
            "stream": True,
        }

        if tools:
            request_body["tools"] = tools

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._default_headers)

        try:
            response = requests.post(
                endpoint,
                json=request_body,
                headers=headers,
                stream=True,
                timeout=self._timeout,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith(b"data: "):
                    data = line[6:].decode("utf-8")
                    if data == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data)

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
                            finish_reason: str = None

                        @dataclass
                        class MockChunk:
                            choices: List[MockChoice]
                            model: str

                        delta_content = ""
                        choices = chunk_data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            delta_content = delta.get("content", "")
                            finish_reason = choices[0].get("finish_reason")

                        yield MockChunk(
                            choices=[MockChoice(
                                message=MockMessage(content=delta_content),
                                finish_reason=finish_reason,
                            )],
                            model=model or self._model,
                        )

                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.ConnectionError as e:
            raise ProviderConnectionError(
                f"无法连接到 {self.name} ({self._base_url}): {e}",
                provider=self.name,
            ) from e
        except requests.exceptions.RequestException as e:
            raise ProviderError(
                f"{self.name} API 调用失败: {e}",
                provider=self.name,
            ) from e

    def stream(
        self,
        messages: List[Any],
        tools: Optional[List[Any]] = None,
        **kwargs,
    ) -> Iterator[NormalizedResponse]:
        """流式调用 API。"""
        converted_messages = self.transport.convert_messages(messages)
        converted_tools = None
        if tools and self.capabilities.supports_tools:
            converted_tools = self.transport.convert_tools(tools)

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
        """非流式调用 API。"""
        from hai_agent.types import ToolCall

        accumulated_content = ""
        accumulated_tool_calls: List[ToolCall] = []
        final_response: Optional[NormalizedResponse] = None

        for chunk in self.stream(messages, tools, **kwargs):
            if chunk.content:
                accumulated_content += chunk.content
            if chunk.tool_calls:
                accumulated_tool_calls.extend(chunk.tool_calls)
            final_response = chunk

        if final_response is None:
            return NormalizedResponse(content="")

        return NormalizedResponse(
            content=accumulated_content,
            tool_calls=accumulated_tool_calls if accumulated_tool_calls else None,
            finish_reason=final_response.finish_reason,
            reasoning=final_response.reasoning,
            usage=final_response.usage,
            model=final_response.model,
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "api_mode": self._api_mode,
            "base_url": self._base_url,
            "model": self._model,
            "capabilities": self.capabilities.to_dict(),
        }

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "CustomProvider":
        """从配置字典创建 Provider。

        Args:
            config: 配置字典

        Returns:
            CustomProvider 实例
        """
        return cls(
            name=config.get("name", "custom"),
            api_mode=config.get("api_mode", "chat_completions"),
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model=config.get("model", "default"),
            timeout=config.get("timeout", 300.0),
            default_headers=config.get("default_headers"),
            supports_tools=config.get("supports_tools", True),
            supports_streaming=config.get("supports_streaming", True),
            supports_vision=config.get("supports_vision", False),
            supports_caching=config.get("supports_caching", False),
            supports_reasoning=config.get("supports_reasoning", False),
        )

    @classmethod
    def from_profile(
        cls,
        profile: ProviderProfile,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ) -> "CustomProvider":
        """从 ProviderProfile 创建 Provider。

        Args:
            profile: ProviderProfile 实例
            api_key: API 密钥（可选，覆盖 profile 的 env_vars）
            base_url: 基础 URL（可选，覆盖 profile 的 base_url）
            **kwargs: 其他参数

        Returns:
            CustomProvider 实例
        """
        # 如果未提供 api_key，尝试从环境变量获取
        if api_key is None:
            api_key = profile.get_api_key()

        return cls(
            name=profile.name,
            api_mode=profile.api_mode,
            api_key=api_key,
            base_url=base_url or profile.base_url,
            default_headers=profile.default_headers,
            supports_tools=profile.supports_tools,
            supports_streaming=profile.supports_streaming,
            supports_vision=profile.supports_vision,
            supports_caching=profile.supports_caching,
            supports_reasoning=profile.supports_reasoning,
            **kwargs,
        )
