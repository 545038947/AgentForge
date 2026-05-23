"""OpenAI Chat Completions Transport。

处理默认 api_mode ('chat_completions')，被约 16 个 OpenAI 兼容的 Provider 使用
（OpenRouter, Nous, NVIDIA, Qwen, Ollama, DeepSeek, xAI, Kimi 等）。

参考 hermes-agent/agent/transports/chat_completions.py 实现。
"""

from __future__ import annotations

import copy
import json
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
        messages: List[Any],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """转换消息格式。

        消息可能是 Message 对象或字典格式。此方法会：
        1. 将 Message 对象转换为字典
        2. 将 Anthropic 风格的 tool_result 转换为 OpenAI 格式
        3. 剥离严格的 chat-completions Provider 会用 HTTP 400/422 拒绝的内部字段

        剥离的字段：
        - tool_name: 工具结果消息上的字段（用于 SQLite FTS 索引）
        - 其他内部元数据字段
        """
        from agentforge.types import Message

        result = []
        for msg in messages:
            # 处理 Message 对象
            if isinstance(msg, Message):
                msg_dict = self._convert_message_to_openai_dict(msg)
            elif isinstance(msg, dict):
                msg_dict = msg
            else:
                # 尝试转换为字典
                if hasattr(msg, "to_dict"):
                    msg_dict = msg.to_dict()
                else:
                    msg_dict = {"role": "user", "content": str(msg)}

            result.append(msg_dict)

        # 检查需要剥离的内部字段
        needs_sanitize = False
        for msg in result:
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
            return result

        # 深拷贝并剥离内部字段
        sanitized = copy.deepcopy(result)
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

    def _convert_message_to_openai_dict(self, msg: "Message") -> Dict[str, Any]:
        """将 Message 对象转换为 OpenAI 格式字典。

        处理 Anthropic 风格的 tool_result 内容块，转换为 OpenAI 的 tool role 格式。
        """
        from agentforge.types import (
            Message,
            TextContent,
            ImageContent,
            ToolUseContent,
            ToolResultContent,
        )

        # 如果是纯文本，直接返回
        if isinstance(msg.content, str):
            result = {"role": msg.role, "content": msg.content}
            if msg.name:
                result["name"] = msg.name
            return result

        # 处理多模态内容
        content_blocks = msg.content
        if not isinstance(content_blocks, list):
            return {"role": msg.role, "content": str(content_blocks)}

        # 检查是否只有 ToolResultContent（需要转换为 tool role）
        if len(content_blocks) == 1 and isinstance(content_blocks[0], ToolResultContent):
            block = content_blocks[0]
            return {
                "role": "tool",
                "tool_call_id": block.tool_use_id,
                "content": block.content,
            }

        # 混合内容：提取各部分
        text_parts = []
        tool_calls = []

        for block in content_blocks:
            if isinstance(block, TextContent):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseContent):
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": block.input if isinstance(block.input, str)
                            else json.dumps(block.input, ensure_ascii=False),
                    }
                })
            elif isinstance(block, ToolResultContent):
                # 多个 tool_result 的情况，转换为单独的消息
                # 但这里我们只能返回一条消息，所以跳过
                # 实际应该在 add_tool_results 时就处理好
                pass
            elif isinstance(block, ImageContent):
                # 图片处理
                pass

        result = {"role": msg.role}
        # OpenAI API 规范允许 assistant 消息没有 content（只有 tool_calls）
        # 但某些 Provider（如 Ollama）要求必须有 content 字段
        # 设置 content 为空字符串以兼容这些 Provider
        result["content"] = "\n".join(text_parts) if text_parts else ""
        if tool_calls:
            result["tool_calls"] = tool_calls

        return result

    def convert_tools(
        self,
        tools: List[Any],
    ) -> List[Dict[str, Any]]:
        """转换工具定义格式。

        将 Tool/ToolSpec 对象转换为 OpenAI 格式字典。
        如果输入已经是字典，则原样返回。
        """
        result = []
        for tool in tools:
            # 如果已经是字典，原样添加
            if isinstance(tool, dict):
                result.append(tool)
            # 如果有 to_openai_tool 方法（ToolSpec）
            elif hasattr(tool, "to_openai_tool"):
                result.append(tool.to_openai_tool())
            # 如果是 Tool 对象，从 spec 获取
            elif hasattr(tool, "spec"):
                result.append(tool.spec.to_openai_tool())
            else:
                # 尝试手动构建
                result.append({
                    "type": "function",
                    "function": {
                        "name": getattr(tool, "name", "unknown"),
                        "description": getattr(tool, "description", ""),
                        "parameters": getattr(tool, "parameters", {"type": "object"}),
                    }
                })
        return result

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

        支持两种响应格式：
        - 完整响应：choice.message
        - 流式响应：choice.delta
        """
        choice = response.choices[0]

        # 处理流式响应（delta）和完整响应（message）
        if hasattr(choice, "delta") and choice.delta is not None:
            msg = choice.delta
        elif hasattr(choice, "message") and choice.message is not None:
            msg = choice.message
        else:
            # 兼容某些 Provider 的非标准响应
            msg = choice

        finish_reason = getattr(choice, "finish_reason", None) or "stop"

        tool_calls = None
        # 检查是否有 tool_calls（可能在 message 或 delta 上）
        raw_tool_calls = getattr(msg, "tool_calls", None)
        if raw_tool_calls:
            tool_calls = []
            for tc in raw_tool_calls:
                # 保留 Provider 特定的额外信息
                tc_provider_data: Dict[str, Any] = {}
                extra = getattr(tc, "extra_content", None)
                if extra is None and hasattr(tc, "model_extra"):
                    extra = (tc.model_extra or {}).get("extra_content")
                if extra is not None:
                    if hasattr(extra, "model_dump"):
                        try:
                            extra = extra.model_dump()
                        except (AttributeError, TypeError, ValueError):
                            pass
                    tc_provider_data["extra_content"] = extra

                # 处理 tool call 的 id 和 function
                # 支持对象和字典两种格式
                if isinstance(tc, dict):
                    tc_id = tc.get("id") or tc.get("index")
                    tc_function = tc.get("function")
                    if tc_function:
                        tc_name = tc_function.get("name", "")
                        tc_args = tc_function.get("arguments", "{}")
                    else:
                        tc_name = tc.get("name", "")
                        tc_args = tc.get("arguments", "{}")
                else:
                    tc_id = getattr(tc, "id", None) or getattr(tc, "index", None)
                    tc_function = getattr(tc, "function", None)
                    if tc_function:
                        tc_name = getattr(tc_function, "name", "")
                        tc_args = getattr(tc_function, "arguments", "{}")
                    else:
                        tc_name = getattr(tc, "name", "")
                        tc_args = getattr(tc, "arguments", "{}")

                tool_calls.append(
                    ToolCall(
                        id=str(tc_id) if tc_id is not None else None,
                        name=tc_name,
                        arguments=tc_args,
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

        # 获取内容
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content", "")

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
