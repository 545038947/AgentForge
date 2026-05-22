"""Ollama Provider 实现。

支持本地和远程 Ollama 服务器，提供 OpenAI-compatible API。
"""

from __future__ import annotations

import logging
import requests
from typing import Any, Dict, Iterator, List, Optional

from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.transports import ChatCompletionsTransport
from agentforge.types import NormalizedResponse, ToolCall, Usage
from agentforge.types.errors import ProviderError, ProviderConnectionError

logger = logging.getLogger(__name__)


# Ollama 默认端点
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(Provider):
    """Ollama Provider。

    支持：
    - 本地 Ollama 服务器（默认 localhost:11434）
    - 远程 Ollama 服务器
    - OpenAI-compatible API（/v1/chat/completions）
    - 流式响应
    - 工具调用（取决于模型能力）
    - 自定义 num_ctx 参数

    使用示例：
        # 使用默认本地服务器
        provider = OllamaProvider(model="llama3.2")

        # 指定远程服务器
        provider = OllamaProvider(
            model="gemma4:31b",
            base_url="http://192.168.1.100:11434/v1",
        )

        # 自定义上下文长度
        provider = OllamaProvider(
            model="llama3.2",
            num_ctx=16384,
        )
    """

    name = "ollama"

    def __init__(
        self,
        api_key: str = "ollama",  # Ollama 不需要 API Key，但 SDK 需要非空值
        base_url: str = OLLAMA_DEFAULT_BASE_URL,
        model: str = "llama3.2",
        timeout: float = 600.0,  # 本地模型可能较慢
        num_ctx: Optional[int] = None,
        num_predict: Optional[int] = None,
        **kwargs,
    ):
        """初始化 Ollama Provider。

        Args:
            api_key: API 密钥（Ollama 不需要，可使用任意非空值）
            base_url: Ollama 服务器地址（默认 http://localhost:11434/v1）
            model: 模型名称（如 llama3.2, gemma4:31b）
            timeout: 超时时间（秒），本地模型建议设置较长
            num_ctx: 上下文长度（可选，覆盖模型默认）
            num_predict: 最大生成 Token 数（可选）
            **kwargs: 其他参数
        """
        self._model = model
        self._timeout = timeout
        self._num_ctx = num_ctx
        self._num_predict = num_predict
        self._kwargs = kwargs
        super().__init__(api_key=api_key, base_url=base_url)

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Provider 能力。

        注意：Ollama 的能力取决于使用的模型。
        这里返回保守的默认值，实际能力需要根据模型判断。
        """
        return ProviderCapabilities(
            supports_tools=True,  # 部分 Ollama 模型支持工具调用
            supports_streaming=True,
            supports_vision=self._check_vision_support(),
            supports_caching=False,
            supports_reasoning=False,
            supports_parallel_tool_calls=False,  # Ollama 不支持并行工具调用
        )

    def _check_vision_support(self) -> bool:
        """检查模型是否支持视觉。"""
        # 常见支持视觉的 Ollama 模型
        vision_models = {
            "llava", "llava:", "moondream", "moondream:",
            "bakllava", "cogvlm", "vision",
        }
        model_lower = self._model.lower()
        return any(vm in model_lower for vm in vision_models)

    def _default_transport(self) -> ChatCompletionsTransport:
        """默认 Transport。

        Ollama 使用 OpenAI-compatible API 格式。
        """
        return ChatCompletionsTransport()

    def _create_client(self) -> Any:
        """创建 API 客户端。"""
        try:
            from openai import OpenAI

            return OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        except ImportError:
            logger.warning(
                "openai SDK 未安装，Ollama Provider 将使用 HTTP 直接调用。"
                "建议安装: pip install openai"
            )
            return None

    def _get_server_url(self) -> str:
        """获取 Ollama 服务器基础 URL（不含 /v1）。"""
        base = self._base_url or OLLAMA_DEFAULT_BASE_URL
        if base.endswith("/v1"):
            return base[:-3].rstrip("/")
        return base.rstrip("/")

    def _query_model_info(self) -> Optional[Dict[str, Any]]:
        """查询模型信息。

        Returns:
            模型信息字典，失败返回 None
        """
        server_url = self._get_server_url()
        try:
            response = requests.post(
                f"{server_url}/api/show",
                json={"name": self._model},
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"查询 Ollama 模型信息失败: {e}")
        return None

    def get_model_context_length(self) -> Optional[int]:
        """获取模型的上下文长度。

        优先级：
        1. 构造函数指定的 num_ctx
        2. Ollama 服务器的模型配置
        3. 返回 None（使用默认值）

        Returns:
            上下文长度，未知返回 None
        """
        # 使用显式配置的值
        if self._num_ctx:
            return self._num_ctx

        # 查询服务器
        model_info = self._query_model_info()
        if model_info:
            # 尝试从参数中获取 num_ctx
            params = model_info.get("parameters", "")
            if "num_ctx" in params:
                for line in params.split("\n"):
                    if "num_ctx" in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            try:
                                return int(parts[-1])
                            except ValueError:
                                pass

            # 尝试从 model_info 中获取 context_length
            model_details = model_info.get("model_info", {})
            for key, value in model_details.items():
                if "context_length" in key.lower():
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        pass

        return None

    def list_available_models(self) -> List[str]:
        """列出服务器上可用的模型。

        Returns:
            模型名称列表
        """
        server_url = self._get_server_url()
        try:
            response = requests.get(
                f"{server_url}/api/tags",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"获取 Ollama 模型列表失败: {e}")
        return []

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
            # 移除 model 从 kwargs 避免重复传递
            http_kwargs = {k: v for k, v in kwargs.items() if k != "model"}
            yield from self._do_stream_http(messages, tools, model, **http_kwargs)
            return

        try:
            # 构建请求参数
            request_params = {
                "model": model,
                "messages": messages,
                "stream": True,
            }

            # 添加 Ollama 特定参数
            if self._num_ctx:
                request_params["num_ctx"] = self._num_ctx
            if self._num_predict:
                request_params["num_predict"] = self._num_predict

            # 添加额外参数（如 temperature）
            for key in ["max_tokens", "temperature", "top_p", "top_k"]:
                if key in kwargs:
                    request_params[key] = kwargs[key]

            if tools:
                request_params["tools"] = tools

            # 执行流式调用
            stream = self._client.chat.completions.create(**request_params)

            for chunk in stream:
                yield chunk

        except Exception as e:
            error_str = str(e).lower()
            if "connection" in error_str or "refused" in error_str:
                raise ProviderConnectionError(
                    f"无法连接到 Ollama 服务器 ({self._base_url}): {e}",
                    provider=self.name,
                ) from e
            else:
                raise ProviderError(
                    f"Ollama API 调用失败: {e}",
                    provider=self.name,
                ) from e

    def _do_stream_http(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: str = None,
        **kwargs,
    ) -> Iterator[Any]:
        """使用 HTTP 直接调用（当 SDK 未安装时）。

        Args:
            messages: 消息列表
            tools: 工具定义
            model: 模型名称
            **kwargs: 其他参数

        Yields:
            模拟的响应对象
        """
        import json
        from dataclasses import dataclass

        # 构建请求
        endpoint = self._base_url.rstrip("/") + "/chat/completions"
        request_body = {
            "model": model or self._model,
            "messages": messages,
            "stream": True,
        }

        if self._num_ctx:
            request_body["num_ctx"] = self._num_ctx
        if tools:
            request_body["tools"] = tools

        try:
            response = requests.post(
                endpoint,
                json=request_body,
                headers={"Content-Type": "application/json"},
                stream=True,
                timeout=self._timeout,
            )
            response.raise_for_status()

            # 解析 SSE 响应
            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith(b"data: "):
                    data = line[6:].decode("utf-8")
                    if data == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data)

                        # 创建模拟响应对象（使用 message 而非 delta，兼容 Transport）
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
                f"无法连接到 Ollama 服务器 ({self._base_url}): {e}",
                provider=self.name,
            ) from e
        except requests.exceptions.Timeout as e:
            raise ProviderError(
                f"Ollama 请求超时 ({self._timeout}s): {e}",
                provider=self.name,
            ) from e
        except requests.exceptions.RequestException as e:
            raise ProviderError(
                f"Ollama API 调用失败: {e}",
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
        """非流式调用 API。

        Args:
            messages: 消息列表
            tools: 工具列表（可选）
            **kwargs: 其他参数

        Returns:
            完整响应
        """
        accumulated_content = ""
        accumulated_tool_calls: List[ToolCall] = []
        final_response: Optional[NormalizedResponse] = None

        for chunk in self.stream(messages, tools, **kwargs):
            # 累积内容
            if chunk.content:
                accumulated_content += chunk.content

            # 累积工具调用
            if chunk.tool_calls:
                accumulated_tool_calls.extend(chunk.tool_calls)

            # 保留最后一个响应用于获取其他字段
            final_response = chunk

        if final_response is None:
            return NormalizedResponse(content="")

        # 返回累积后的响应
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
            "model": self._model,
            "base_url": self._base_url,
            "num_ctx": self._num_ctx,
            "capabilities": self.capabilities.to_dict(),
        }
