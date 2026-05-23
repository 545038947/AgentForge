"""Transport 抽象基类。

定义 Provider 协议转换的统一接口，参考 hermes-agent/agent/transports/base.py 设计。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from hai_agent.types import NormalizedResponse


class Transport(ABC):
    """Transport 抽象基类，定义协议转换接口。

    Transport 层采用策略模式：
    - Provider 持有 Transport 实例（可替换）
    - Transport 负责特定 API 格式的转换
    - 不同 Provider 可共享相同 Transport

    职责边界：
    - Transport：协议转换、响应标准化
    - Provider：API 连接、认证、错误处理、重试

    例如：
    - OpenAI Provider 使用 ChatCompletionsTransport
    - Moonshot Provider 使用 ChatCompletionsTransport + MoonshotAdapter
    - Anthropic Provider 使用 AnthropicTransport
    """

    @property
    @abstractmethod
    def api_mode(self) -> str:
        """返回 API 模式标识。

        常见值：
        - "chat_completions": OpenAI Chat Completions API
        - "anthropic_messages": Anthropic Messages API
        - "bedrock_converse": AWS Bedrock Converse API
        """
        ...

    @abstractmethod
    def convert_messages(
        self,
        messages: List[Dict[str, Any]],
        **kwargs,
    ) -> Any:
        """转换消息格式。

        输入：OpenAI 格式的消息列表
        输出：Provider 原生格式

        Args:
            messages: OpenAI 格式的消息列表
            **kwargs: 额外参数（如 system_prompt 分离）

        Returns:
            Provider 原生格式的消息结构
        """
        ...

    @abstractmethod
    def convert_tools(
        self,
        tools: List[Dict[str, Any]],
    ) -> Any:
        """转换工具定义格式。

        输入：OpenAI 格式的工具定义
        输出：Provider 原生格式

        Args:
            tools: OpenAI 格式的工具定义列表

        Returns:
            Provider 原生格式的工具定义
        """
        ...

    @abstractmethod
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """构建 API 调用参数。

        整合消息、工具、模型参数等，返回完整的 kwargs。

        Args:
            model: 模型名称
            messages: 消息列表（已转换格式）
            tools: 工具定义列表（已转换格式）
            **params: 额外参数（max_tokens, temperature 等）

        Returns:
            可直接传递给 SDK 客户端的参数字典
        """
        ...

    @abstractmethod
    def normalize_response(
        self,
        response: Any,
        **kwargs,
    ) -> NormalizedResponse:
        """标准化响应。

        输入：Provider 原生响应对象
        输出：NormalizedResponse 统一格式

        Args:
            response: Provider SDK 返回的原始响应对象
            **kwargs: 额外上下文

        Returns:
            标准化的 NormalizedResponse 对象
        """
        ...

    # ── 可选方法 ──────────────────────────────────────────

    def validate_response(self, response: Any) -> bool:
        """验证响应结构是否有效。

        Args:
            response: 原始响应对象

        Returns:
            True 如果响应有效，False 如果应视为无效
        """
        return True

    def extract_cache_stats(
        self,
        response: Any,
    ) -> Optional[Dict[str, int]]:
        """提取缓存命中统计。

        Args:
            response: 原始响应对象

        Returns:
            包含 cached_tokens 和 creation_tokens 的字典，或 None
        """
        return None

    def map_finish_reason(self, raw_reason: str) -> str:
        """映射 Provider 特定的结束原因到标准值。

        Args:
            raw_reason: Provider 返回的原始结束原因

        Returns:
            标准化的结束原因（"stop", "tool_calls", "length", "content_filter"）
        """
        return raw_reason


# ── Transport 注册表 ─────────────────────────────────────

_transport_registry: Dict[str, type[Transport]] = {}


def register_transport(api_mode: str, transport_class: type[Transport]) -> None:
    """注册 Transport 类。

    Args:
        api_mode: API 模式标识
        transport_class: Transport 类
    """
    _transport_registry[api_mode] = transport_class


def get_transport(api_mode: str) -> Optional[type[Transport]]:
    """获取 Transport 类。

    Args:
        api_mode: API 模式标识

    Returns:
        Transport 类，如果未注册则返回 None
    """
    return _transport_registry.get(api_mode)


def list_transports() -> List[str]:
    """列出所有已注册的 API 模式。"""
    return list(_transport_registry.keys())
