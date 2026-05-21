"""OpenAI Chat Completions Transport。

处理默认 api_mode ('chat_completions')，被约 16 个 OpenAI 兼容的 Provider 使用
（OpenRouter, Nous, NVIDIA, Qwen, Ollama, DeepSeek, xAI, Kimi 等）。

参考 hermes-agent/agent/transports/chat_completions.py 实现。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from agentforge.providers.transports.base import Transport
from agentforge.types import NormalizedResponse, ToolCall, Usage


class ChatCompletionsTransport(Transport):
    """api_mode='chat_completions' 的 Transport。

    OpenAI 兼容 Provider 的默认路径。消息和工具已经是 OpenAI 格式，
    convert_messages 和 convert_tools 几乎是恒等转换。
    """

    @property
    def api_mode(self) -> str:
        return "chat_completions"

    def convert_messages(
        self,
        messages: List[Dict[str, Any]],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """转换消息格式。

        消息已经是 OpenAI 格式 —— 剥离严格的 chat-completions Provider
        会用 HTTP 400/422 拒绝的内部字段。

        剥离的字段：
        - tool_name: 工具结果消息上的字段（用于 SQLite FTS 索引）
        - 其他内部元数据字段
        """
        needs_sanitize = False
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            # 检查需要剥离的字段
            if "tool_name" in msg:
                needs_sanitize = True
                break
            # 检查 tool_calls 中的内部字段
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict) and (
                        "call_id" in tc or "response_item_id" in tc
                    ):
                        needs_sanitize = True
                        break
                if needs_sanitize:
                    break

        if not needs_sanitize:
            return messages

        # 深拷贝并剥离内部字段
        sanitized = copy.deepcopy(messages)
        for msg in sanitized:
            if not isinstance(msg, dict):
                continue
            msg.pop("tool_name", None)
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc.pop("call_id", None)
                        tc.pop("response_item_id", None)
        return sanitized

    def convert_tools(
        self,
        tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """转换工具定义格式。

        工具已经是 OpenAI 格式 —— 恒等转换。
        """
        return tools

    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """构建 chat.completions.create() 参数。

        Args:
            model: 模型名称
            messages: 消息列表
            tools: 工具定义列表
            **params: 额外参数
                - timeout: API 调用超时
                - max_tokens: 最大输出 Token
                - temperature: 温度参数
                - stream: 是否流式
                - extra_body: 额外请求体参数
                - reasoning_config: 推理配置
                - request_overrides: 请求覆盖参数

        Returns:
            可传递给 SDK 客户端的参数字典
        """
        # 消息预处理（剥离内部字段）
        sanitized = self.convert_messages(messages)

        api_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": sanitized,
        }

        # 超时
        timeout = params.get("timeout")
        if timeout is not None:
            api_kwargs["timeout"] = timeout

        # 工具
        if tools:
            api_kwargs["tools"] = tools

        # max_tokens
        max_tokens = params.get("max_tokens")
        if max_tokens is not None:
            api_kwargs["max_tokens"] = max_tokens

        # temperature
        temperature = params.get("temperature")
        if temperature is not None:
            api_kwargs["temperature"] = temperature

        # 流式
        stream = params.get("stream")
        if stream is not None:
            api_kwargs["stream"] = stream

        # extra_body（额外请求体参数）
        extra_body: Dict[str, Any] = {}
        extra_body_additions = params.get("extra_body")
        if extra_body_additions:
            extra_body.update(extra_body_additions)

        # 推理配置（部分 Provider 支持）
        reasoning_config = params.get("reasoning_config")
        if reasoning_config and isinstance(reasoning_config, dict):
            if reasoning_config.get("enabled"):
                extra_body["reasoning"] = {
                    "enabled": True,
                    "effort": reasoning_config.get("effort", "medium"),
                }

        if extra_body:
            api_kwargs["extra_body"] = extra_body

        # 请求覆盖参数
        request_overrides = params.get("request_overrides")
        if request_overrides:
            api_kwargs.update(request_overrides)

        return api_kwargs

    def normalize_response(
        self,
        response: Any,
        **kwargs,
    ) -> NormalizedResponse:
        """标准化 OpenAI ChatCompletion 为 NormalizedResponse。

        对于 chat_completions，这几乎是恒等转换 —— 响应已经是 OpenAI 格式。
        tool_calls 上的 extra_content（Gemini thought_signature）通过
        ToolCall.provider_data 保留。
        """
        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason or "stop"

        tool_calls = None
        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                # 保留 Provider 特定的额外信息
                tc_provider_data: Dict[str, Any] = {}
                extra = getattr(tc, "extra_content", None)
                if extra is None and hasattr(tc, "model_extra"):
                    extra = (tc.model_extra or {}).get("extra_content")
                if extra is not None:
                    if hasattr(extra, "model_dump"):
                        try:
                            extra = extra.model_dump()
                        except Exception:
                            pass
                    tc_provider_data["extra_content"] = extra

                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                        provider_data=tc_provider_data or None,
                    )
                )

        usage = None
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = Usage(
                prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                total_tokens=getattr(u, "total_tokens", 0) or 0,
            )

        # 保留推理字段
        reasoning = getattr(msg, "reasoning", None)
        reasoning_content = getattr(msg, "reasoning_content", None)
        if reasoning_content is None and hasattr(msg, "model_extra"):
            model_extra = getattr(msg, "model_extra", None) or {}
            if isinstance(model_extra, dict) and "reasoning_content" in model_extra:
                reasoning_content = model_extra["reasoning_content"]

        provider_data: Dict[str, Any] = {}
        if reasoning_content is not None:
            provider_data["reasoning_content"] = reasoning_content
        rd = getattr(msg, "reasoning_details", None)
        if rd:
            provider_data["reasoning_details"] = rd

        return NormalizedResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            reasoning=reasoning,
            usage=usage,
            provider_data=provider_data or None,
        )

    def validate_response(self, response: Any) -> bool:
        """检查响应是否有有效的 choices。"""
        if response is None:
            return False
        if not hasattr(response, "choices") or response.choices is None:
            return False
        if not response.choices:
            return False
        return True

    def extract_cache_stats(
        self,
        response: Any,
    ) -> Optional[Dict[str, int]]:
        """从 prompt_tokens_details 提取缓存统计。"""
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        details = getattr(usage, "prompt_tokens_details", None)
        if details is None:
            return None
        cached = getattr(details, "cached_tokens", 0) or 0
        written = getattr(details, "cache_write_tokens", 0) or 0
        if cached or written:
            return {"cached_tokens": cached, "creation_tokens": written}
        return None


# 自动注册
from agentforge.providers.transports import register_transport
register_transport("chat_completions", ChatCompletionsTransport)
