"""Anthropic Messages API Transport。

实现 Anthropic 特定的消息和工具转换。
参考 hermes-agent/agent/transports/anthropic.py 和 anthropic_adapter.py。
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from hai_agent.providers.transports.base import Transport
from hai_agent.types import NormalizedResponse, ToolCall, Usage

logger = logging.getLogger(__name__)


# Anthropic stop_reason 到 OpenAI finish_reason 的映射
_STOP_REASON_MAP = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "stop_sequence": "stop",
    "refusal": "content_filter",
    "model_context_window_exceeded": "length",
}


class AnthropicTransport(Transport):
    """Anthropic Messages API Transport。

    处理：
    - 消息格式转换（OpenAI → Anthropic）
    - 工具格式转换
    - 响应标准化
    - Thinking block 处理
    - Prompt Caching 支持
    """

    @property
    def api_mode(self) -> str:
        """API 模式标识。"""
        return "anthropic_messages"

    def convert_messages(
        self,
        messages: List[Any],
        **kwargs,
    ) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
        """转换消息为 Anthropic 格式。

        Anthropic 将 system 消息作为单独参数传递。

        Args:
            messages: OpenAI 格式消息列表
            **kwargs: 其他参数（base_url, model 等）

        Returns:
            (system_prompt, anthropic_messages) 元组
        """
        system = None
        result = []

        for m in messages:
            # 处理 Message 对象
            if hasattr(m, "to_dict"):
                m = m.to_dict()
            elif hasattr(m, "role") and hasattr(m, "content"):
                m = {
                    "role": m.role,
                    "content": m.content,
                    "tool_calls": getattr(m, "tool_calls", None),
                    "tool_call_id": getattr(m, "tool_call_id", None),
                }

            role = m.get("role", "user")
            content = m.get("content", "")

            # System 消息单独处理
            if role == "system":
                if isinstance(content, list):
                    # 检查是否有 cache_control
                    has_cache = any(
                        p.get("cache_control") for p in content if isinstance(p, dict)
                    )
                    if has_cache:
                        system = [p for p in content if isinstance(p, dict)]
                    else:
                        system = "\n".join(
                            p.get("text", "") for p in content if p.get("type") == "text"
                        )
                else:
                    system = content
                continue

            # Assistant 消息
            if role == "assistant":
                blocks = []

                # 处理 reasoning_content（thinking block）
                reasoning_content = m.get("reasoning_content")
                if isinstance(reasoning_content, str) and reasoning_content:
                    blocks.append({"type": "thinking", "thinking": reasoning_content})

                # 处理内容
                if content:
                    if isinstance(content, list):
                        converted = self._convert_content_blocks(content)
                        blocks.extend(converted)
                    else:
                        blocks.append({"type": "text", "text": str(content)})

                # 处理工具调用
                for tc in m.get("tool_calls", []) or []:
                    if not tc or not isinstance(tc, dict):
                        continue
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    try:
                        parsed_args = json.loads(args) if isinstance(args, str) else args
                    except (json.JSONDecodeError, ValueError):
                        parsed_args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": self._sanitize_tool_id(tc.get("id", "")),
                        "name": fn.get("name", ""),
                        "input": parsed_args,
                    })

                # Anthropic 拒绝空的 assistant 内容
                if not blocks:
                    blocks = [{"type": "text", "text": "(empty)"}]

                result.append({"role": "assistant", "content": blocks})
                continue

            # Tool 消息（工具结果）
            if role == "tool":
                tool_result_content = self._convert_tool_result(content)
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": self._sanitize_tool_id(m.get("tool_call_id", "")),
                    "content": tool_result_content,
                }
                if isinstance(m.get("cache_control"), dict):
                    tool_result["cache_control"] = dict(m["cache_control"])

                # 合并连续的 tool 结果到一个 user 消息
                if result and result[-1]["role"] == "user":
                    last_content = result[-1].get("content", [])
                    if isinstance(last_content, list):
                        last_content.append(tool_result)
                        result[-1]["content"] = last_content
                        continue

                result.append({"role": "user", "content": [tool_result]})
                continue

            # User 消息
            if role == "user":
                if isinstance(content, list):
                    blocks = self._convert_content_blocks(content)
                elif isinstance(content, str):
                    blocks = [{"type": "text", "text": content}]
                else:
                    blocks = [{"type": "text", "text": str(content)}]

                result.append({"role": "user", "content": blocks})
                continue

        return system, result

    def convert_tools(self, tools: List[Any]) -> List[Dict[str, Any]]:
        """转换工具为 Anthropic input_schema 格式。

        Args:
            tools: OpenAI 格式工具列表

        Returns:
            Anthropic 格式工具列表
        """
        result = []
        for tool in tools:
            # 处理 ToolSpec 对象
            if hasattr(tool, "to_spec"):
                spec = tool.to_spec()
                tool_dict = {
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": spec.parameters,
                }
            elif isinstance(tool, dict):
                # OpenAI 格式转换
                fn = tool.get("function", {})
                params = fn.get("parameters", {})
                if not params:
                    params = {"type": "object", "properties": {}}
                tool_dict = {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": params,
                }
            else:
                continue

            # 清理 input_schema（移除 Anthropic 不支持的字段）
            schema = tool_dict.get("input_schema", {})
            if isinstance(schema, dict):
                schema = self._sanitize_tool_schema(schema)
                tool_dict["input_schema"] = schema

            result.append(tool_dict)

        # 去重（Anthropic 拒绝重复的工具名）
        seen = set()
        unique = []
        for t in result:
            name = t.get("name", "")
            if name not in seen:
                seen.add(name)
                unique.append(t)

        return unique

    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """构建 Anthropic messages.create() 参数。

        Args:
            model: 模型名称
            messages: 已转换的消息列表
            tools: 已转换的工具列表
            **params: 其他参数

        Returns:
            Anthropic API 参数字典
        """
        # 获取 system 和 messages
        system, anthropic_messages = self.convert_messages(messages, **params)

        # 基础参数
        kwargs = {
            "model": model,
            "messages": anthropic_messages,
        }

        # System prompt
        if system:
            kwargs["system"] = system

        # Max tokens（Anthropic 必需）
        max_tokens = params.get("max_tokens", 16384)
        kwargs["max_tokens"] = self._resolve_max_tokens(max_tokens, model)

        # 工具
        if tools:
            kwargs["tools"] = tools
            tool_choice = params.get("tool_choice")
            if tool_choice:
                kwargs["tool_choice"] = {"type": tool_choice}

        # Thinking/Reasoning 配置
        reasoning_config = params.get("reasoning_config")
        if reasoning_config:
            kwargs["thinking"] = reasoning_config

        # 流式
        if params.get("stream"):
            kwargs["stream"] = True

        # 其他参数
        for key in ["temperature", "top_p", "top_k"]:
            if key in params and params[key] is not None:
                kwargs[key] = params[key]

        return kwargs

    def normalize_response(
        self,
        response: Any,
        **kwargs,
    ) -> NormalizedResponse:
        """标准化 Anthropic 响应。

        Args:
            response: Anthropic API 响应
            **kwargs: 其他参数

        Returns:
            NormalizedResponse 对象
        """
        text_parts = []
        reasoning_parts = []
        reasoning_details = []
        tool_calls = []

        # 处理内容块
        content_blocks = getattr(response, "content", [])
        for block in content_blocks:
            block_type = getattr(block, "type", None)

            if block_type == "text":
                text = getattr(block, "text", "")
                if text:
                    text_parts.append(text)

            elif block_type == "thinking":
                thinking = getattr(block, "thinking", "")
                if thinking:
                    reasoning_parts.append(thinking)
                # 收集 thinking block 详情
                block_dict = self._block_to_dict(block)
                if block_dict:
                    reasoning_details.append(block_dict)

            elif block_type == "tool_use":
                tool_id = getattr(block, "id", "")
                name = getattr(block, "name", "")
                input_data = getattr(block, "input", {})
                tool_calls.append(
                    ToolCall(
                        id=tool_id,
                        name=name,
                        arguments=json.dumps(input_data),
                    )
                )

        # Finish reason
        stop_reason = getattr(response, "stop_reason", None)
        finish_reason = _STOP_REASON_MAP.get(stop_reason, "stop")

        # Usage
        usage = None
        usage_obj = getattr(response, "usage", None)
        if usage_obj:
            usage = Usage(
                prompt_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                total_tokens=getattr(usage_obj, "input_tokens", 0) + getattr(usage_obj, "output_tokens", 0),
                cached_tokens=getattr(usage_obj, "cache_read_input_tokens", 0) or 0,
            )

        # Provider data
        provider_data = {}
        if reasoning_details:
            provider_data["reasoning_details"] = reasoning_details

        return NormalizedResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            reasoning="\n\n".join(reasoning_parts) if reasoning_parts else None,
            usage=usage,
            provider_data=provider_data or None,
            model=getattr(response, "model", None),
        )

    def validate_response(self, response: Any) -> bool:
        """验证 Anthropic 响应结构。

        空内容列表在 stop_reason == "end_turn" 时是合法的。
        """
        if response is None:
            return False
        content_blocks = getattr(response, "content", None)
        if not isinstance(content_blocks, list):
            return False
        if not content_blocks:
            return getattr(response, "stop_reason", None) == "end_turn"
        return True

    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        """提取缓存统计信息。"""
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        if cached or written:
            return {"cached_tokens": cached, "creation_tokens": written}
        return None

    def map_finish_reason(self, raw_reason: str) -> str:
        """映射 Anthropic stop_reason 到 OpenAI finish_reason。"""
        return _STOP_REASON_MAP.get(raw_reason, "stop")

    # ── 辅助方法 ──────────────────────────────────────────

    def _convert_content_blocks(self, content: List[Any]) -> List[Dict[str, Any]]:
        """转换内容块为 Anthropic 格式。"""
        result = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "text")

                if block_type == "text":
                    text = block.get("text", "")
                    result.append({"type": "text", "text": text})

                elif block_type == "image_url":
                    url = block.get("image_url", {})
                    image_url = url.get("url", "")
                    if image_url.startswith("data:"):
                        # Base64 图片
                        import base64
                        try:
                            # 解析 data URL
                            _, data = image_url.split(",", 1)
                            media_type = image_url.split(";")[0].split(":")[1]
                            result.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": data,
                                },
                            })
                        except (ValueError, TypeError, OSError):
                            logger.warning(f"无法解析图片 URL: {image_url[:50]}")
                    else:
                        # URL 图片（Anthropic 不直接支持，需要下载）
                        logger.warning(f"Anthropic 不支持 URL 图片: {image_url[:50]}")

            elif isinstance(block, str):
                result.append({"type": "text", "text": block})

        return result

    def _convert_tool_result(self, content: Any) -> Any:
        """转换工具结果内容。"""
        if isinstance(content, dict) and content.get("_multimodal"):
            blocks = self._convert_content_blocks(content.get("content", []))
            if not blocks and content.get("text_summary"):
                return str(content["text_summary"])
            return blocks

        if isinstance(content, list):
            converted = self._convert_content_blocks(content)
            if any(b.get("type") == "image" for b in converted):
                return converted
            # 纯文本列表
            return "\n".join(b.get("text", "") for b in converted if b.get("type") == "text")

        if isinstance(content, str):
            return content

        return json.dumps(content) if content else "(no output)"

    def _sanitize_tool_id(self, tool_id: str) -> str:
        """清理工具调用 ID。

        Anthropic 要求 tool_use_id 格式正确。
        """
        if not tool_id:
            return f"tool_{id(tool_id)}"
        # 移除可能导致问题的字符
        return tool_id.strip()

    def _sanitize_tool_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """清理工具 schema。

        Anthropic 不支持某些 JSON Schema 字段。
        """
        # 深拷贝避免修改原始数据
        result = copy.deepcopy(schema)

        # Anthropic 不支持的字段
        unsupported = {"$schema", "additionalItems", "definitions", "$ref", "$defs"}
        for key in unsupported:
            if key in result:
                del result[key]

        # 清理 properties
        props = result.get("properties", {})
        if isinstance(props, dict):
            for prop_name, prop_def in props.items():
                if isinstance(prop_def, dict):
                    # 移除 unsupported 字段
                    for key in unsupported:
                        if key in prop_def:
                            del prop_def[key]
                    # Anthropic 对 format 支持有限
                    if prop_def.get("format") in {"uri", "email", "hostname"}:
                        del prop_def["format"]

        return result

    def _resolve_max_tokens(self, requested: Any, model: str) -> int:
        """解析 max_tokens 参数。"""
        if isinstance(requested, int) and requested > 0:
            return requested
        # 默认值
        return 16384

    def _block_to_dict(self, block: Any) -> Optional[Dict[str, Any]]:
        """将 block 对象转换为字典。"""
        result = {}
        for attr in ["type", "thinking", "signature", "redacted_data"]:
            val = getattr(block, attr, None)
            if val is not None:
                result[attr] = val
        return result if result else None