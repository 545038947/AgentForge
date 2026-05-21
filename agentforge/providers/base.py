"""Provider 抽象基类和能力定义。

定义 Provider 的统一接口，参考 hermes-agent 的 Provider 设计模式。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from agentforge.types import NormalizedResponse, ToolSpec


@dataclass
class ProviderCapabilities:
    """Provider 能力声明。

    声明式设计：Provider 声明支持哪些特性，
    Agent/框架根据能力声明选择行为。

    参考 hermes-agent/agent/models_dev.py 的 ModelInfo 设计。
    """
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_caching: bool = False
    supports_parallel_tool_calls: bool = True
    supports_structured_output: bool = False
    supports_pdf: bool = False
    supports_audio: bool = False

    def supports(self, feature: str) -> bool:
        """检查是否支持指定特性。

        Args:
            feature: 特性名称

        Returns:
            True 如果支持该特性
        """
        feature_map = {
            "tools": self.supports_tools,
            "streaming": self.supports_streaming,
            "vision": self.supports_vision,
            "reasoning": self.supports_reasoning,
            "caching": self.supports_caching,
            "parallel_tool_calls": self.supports_parallel_tool_calls,
            "structured_output": self.supports_structured_output,
            "pdf": self.supports_pdf,
            "audio": self.supports_audio,
        }
        return feature_map.get(feature, False)

    def to_dict(self) -> Dict[str, bool]:
        """转换为字典格式。"""
        return {
            "tools": self.supports_tools,
            "streaming": self.supports_streaming,
            "vision": self.supports_vision,
            "reasoning": self.supports_reasoning,
            "caching": self.supports_caching,
            "parallel_tool_calls": self.supports_parallel_tool_calls,
            "structured_output": self.supports_structured_output,
            "pdf": self.supports_pdf,
            "audio": self.supports_audio,
        }


class Provider(ABC):
    """Provider 抽象基类，负责与 LLM API 交互。

    Provider 与 Transport 的职责分离：
    - Provider：API 连接、认证、错误处理、重试
    - Transport：协议转换、响应标准化

    Provider 持有 Transport 实例，通过组合而非继承实现协议适配。

    使用示例：
        provider = OpenAIProvider(api_key="sk-xxx")
        response = provider.complete(messages=[...], tools=[...])
    """

    name: str  # Provider 名称标识
    capabilities: ProviderCapabilities  # 能力声明

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        transport: Optional[Any] = None,
        settings: Optional[Any] = None,
    ):
        """初始化 Provider。

        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选，用于自定义端点）
            transport: Transport 实例（可选，默认使用 _default_transport）
            settings: Provider 配置（可选）
        """
        self._api_key = api_key
        self._base_url = base_url
        self._settings = settings
        self.transport = transport or self._default_transport()
        self._client = self._create_client()

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称标识。"""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Provider 能力声明。"""
        ...

    @abstractmethod
    def _default_transport(self) -> Any:
        """返回默认 Transport 实例。

        子类实现此方法返回适合该 Provider 的 Transport。
        """
        ...

    @abstractmethod
    def _create_client(self) -> Any:
        """创建 API 客户端实例。

        子类实现此方法创建 SDK 客户端。
        """
        ...

    @abstractmethod
    def _do_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """执行流式 API 调用，返回原生响应流。

        子类实现此方法调用底层 SDK 的流式 API。

        Args:
            messages: 已转换格式的消息列表
            tools: 已转换格式的工具定义
            **kwargs: 其他 API 参数

        Yields:
            原生响应对象（流式）
        """
        ...

    def stream(
        self,
        messages: List[Any],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs,
    ) -> Iterator[NormalizedResponse]:
        """流式调用 API，返回标准化响应流。

        流程：
        1. Transport 转换消息和工具
        2. Transport 构建 kwargs
        3. Provider 执行流式调用
        4. Transport 标准化每个响应

        Args:
            messages: 消息列表
            tools: 工具定义列表
            **kwargs: 其他参数（max_tokens, temperature 等）

        Yields:
            标准化的 NormalizedResponse 对象
        """
        # 转换消息
        converted_messages = self.transport.convert_messages(messages)

        # 转换工具
        converted_tools = None
        if tools and self.capabilities.supports_tools:
            converted_tools = self.transport.convert_tools(tools)

        # 构建 kwargs
        api_kwargs = self.transport.build_kwargs(
            model=kwargs.get("model", self._get_default_model()),
            messages=converted_messages,
            tools=converted_tools,
            **kwargs,
        )

        # 执行流式调用
        for raw_response in self._do_stream(
            messages=converted_messages,
            tools=converted_tools,
            **api_kwargs,
        ):
            yield self.transport.normalize_response(raw_response)

    def complete(
        self,
        messages: List[Any],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs,
    ) -> NormalizedResponse:
        """非流式调用，消费流式响应返回最终结果。

        Args:
            messages: 消息列表
            tools: 工具定义列表
            **kwargs: 其他参数

        Returns:
            最终的 NormalizedResponse 对象
        """
        final_response = None
        for response in self.stream(messages, tools, **kwargs):
            final_response = response
        return final_response

    def supports(self, feature: str) -> bool:
        """检查是否支持某特性。

        Args:
            feature: 特性名称

        Returns:
            True 如果支持该特性
        """
        return self.capabilities.supports(feature)

    def _get_default_model(self) -> str:
        """获取默认模型名称。

        子类可覆盖此方法。
        """
        if self._settings and hasattr(self._settings, "default_model"):
            return self._settings.default_model
        return ""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
