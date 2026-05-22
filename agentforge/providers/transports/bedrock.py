"""AWS Bedrock Converse API Transport。

支持 AWS Bedrock Converse API 协议适配。
Bedrock 使用 boto3 客户端（非 OpenAI SDK），Transport 负责格式转换和响应标准化。

参考 hermes-agent/agent/transports/bedrock.py。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agentforge.providers.transports.base import Transport
from agentforge.types import NormalizedResponse, ToolCall, Usage

logger = logging.getLogger(__name__)


class BedrockTransport(Transport):
    """Bedrock Converse API Transport。

    支持 api_mode='bedrock_converse'。
    """

    @property
    def api_mode(self) -> str:
        return "bedrock_converse"

    def convert_messages(self, messages: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """将 OpenAI 消息转换为 Bedrock Converse 格式。

        Bedrock Converse 格式：
        - system 消息单独处理
        - user/assistant 消息使用 content blocks
        - 图片使用 image block
        - 工具结果使用 toolResult block
        """
        converted = []
        system_prompt = None

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # 系统消息单独处理
            if role == "system":
                system_prompt = content if isinstance(content, str) else self._extract_text(content)
                continue

            # 转换 content
            if isinstance(content, str):
                content_blocks = [{"text": content}]
            elif isinstance(content, list):
                content_blocks = self._convert_content_blocks(content)
            else:
                content_blocks = [{"text": str(content)}]

            # 工具调用结果
            if role == "tool":
                tool_result = self._convert_tool_result(msg)
                if tool_result:
                    converted.append({
                        "role": "user",
                        "content": [tool_result],
                    })
                continue

            # 工具调用请求
            tool_calls = msg.get("tool_calls")
            if role == "assistant" and tool_calls:
                tool_use_blocks = self._convert_tool_calls_to_bedrock(tool_calls)
                content_blocks.extend(tool_use_blocks)

            converted.append({
                "role": role,
                "content": content_blocks,
            })

        return converted

    def convert_tools(self, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """将 OpenAI 工具模式转换为 Bedrock toolConfig。

        Bedrock toolConfig 格式：
        {
            "tools": [
                {
                    "toolSpec": {
                        "name": "...",
                        "description": "...",
                        "inputSchema": {"json": {...}}
                    }
                }
            ]
        }
        """
        bedrock_tools = []

        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                bedrock_tools.append({
                    "toolSpec": {
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "inputSchema": {
                            "json": func.get("parameters", {}),
                        },
                    }
                })

        return {"tools": bedrock_tools}

    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """构建 Bedrock converse() 参数。

        Args:
            model: 模型 ID（Bedrock ARN 或模型名）
            messages: 消息列表
            tools: 工具定义
            **params: 其他参数
                - max_tokens: 输出 token 限制（默认 4096）
                - temperature: 温度参数
                - region: AWS 区域
                - guardrail_config: Bedrock guardrails 配置
        """
        converted_messages = self.convert_messages(messages)

        kwargs = {
            "modelId": model,
            "messages": converted_messages,
            "inferenceConfig": {
                "maxTokens": params.get("max_tokens", 4096),
            },
        }

        if "temperature" in params:
            kwargs["inferenceConfig"]["temperature"] = params["temperature"]

        if tools:
            kwargs["toolConfig"] = self.convert_tools(tools)

        # Sentinel keys 用于分发
        kwargs["__bedrock_converse__"] = True
        kwargs["__bedrock_region__"] = params.get("region", "us-east-1")

        return kwargs

    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """将 Bedrock 响应标准化为 NormalizedResponse。

        Bedrock 响应格式：
        {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "..."}]
                }
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 20}
        }
        """
        if response is None:
            return NormalizedResponse(content="")

        # 处理原始 boto3 dict
        if isinstance(response, dict):
            return self._normalize_dict_response(response)

        # 处理已标准化的对象
        if hasattr(response, "choices"):
            return self._normalize_object_response(response)

        return NormalizedResponse(content=str(response))

    def validate_response(self, response: Any) -> bool:
        """验证 Bedrock 响应结构。"""
        if response is None:
            return False
        if isinstance(response, dict):
            return "output" in response
        if hasattr(response, "choices"):
            return bool(response.choices)
        return False

    def map_finish_reason(self, raw_reason: str) -> str:
        """将 Bedrock stopReason 映射到 OpenAI finish_reason。"""
        _MAP = {
            "end_turn": "stop",
            "tool_use": "tool_calls",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "guardrail_intervened": "content_filter",
            "content_filtered": "content_filter",
        }
        return _MAP.get(raw_reason, "stop")

    def _convert_content_blocks(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换 OpenAI content blocks 到 Bedrock 格式。"""
        converted = []
        for block in blocks:
            block_type = block.get("type", "text")

            if block_type == "text":
                converted.append({"text": block.get("text", "")})
            elif block_type == "image_url":
                # Bedrock 图片格式
                image_url = block.get("image_url", {})
                url = image_url.get("url", "")
                if url.startswith("data:"):
                    # Base64 图片
                    import base64
                    mime_end = url.index(";base64,")
                    mime_type = url[5:mime_end]
                    data = url[mime_end + 8:]
                    converted.append({
                        "image": {
                            "format": mime_type.split("/")[-1],
                            "source": {"bytes": base64.b64decode(data)},
                        }
                    })
            elif block_type == "image":
                converted.append({"image": block.get("image", {})})

        return converted

    def _convert_tool_result(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """转换工具调用结果到 Bedrock toolResult 格式。"""
        tool_call_id = msg.get("tool_call_id", "")
        content = msg.get("content", "")

        return {
            "toolResult": {
                "toolUseId": tool_call_id,
                "content": [{"text": content if isinstance(content, str) else str(content)}],
            }
        }

    def _convert_tool_calls_to_bedrock(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换 OpenAI tool_calls 到 Bedrock toolUse 格式。"""
        blocks = []
        for tc in tool_calls:
            func = tc.get("function", {})
            blocks.append({
                "toolUse": {
                    "toolUseId": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": self._parse_json_args(func.get("arguments", "{}")),
                }
            })
        return blocks

    def _normalize_dict_response(self, response: Dict[str, Any]) -> NormalizedResponse:
        """标准化 dict 格式的 Bedrock 响应。"""
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        # 提取文本内容
        text_content = ""
        tool_calls = []
        reasoning = None

        for block in content_blocks:
            if "text" in block:
                text_content += block["text"]
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(ToolCall(
                    id=tu.get("toolUseId", ""),
                    name=tu.get("name", ""),
                    arguments=self._json_dumps(tu.get("input", {})),
                ))
            elif "reasoning" in block:
                reasoning = block["reasoning"]

        # 提取 usage
        usage_data = response.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("inputTokens", 0),
            completion_tokens=usage_data.get("outputTokens", 0),
            total_tokens=usage_data.get("inputTokens", 0) + usage_data.get("outputTokens", 0),
        ) if usage_data else None

        # 提取 finish_reason
        stop_reason = response.get("stopReason", "end_turn")
        finish_reason = self.map_finish_reason(stop_reason)

        return NormalizedResponse(
            content=text_content,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            reasoning=reasoning,
            usage=usage,
        )

    def _normalize_object_response(self, response: Any) -> NormalizedResponse:
        """标准化对象格式的响应。"""
        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason or "stop"

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in msg.tool_calls
            ]

        usage = None
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = Usage(
                prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                total_tokens=getattr(u, "total_tokens", 0) or 0,
            )

        reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)

        return NormalizedResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            reasoning=reasoning,
            usage=usage,
        )

    def _extract_text(self, content: Any) -> str:
        """从 content blocks 提取文本。"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            return " ".join(texts)
        return str(content)

    def _parse_json_args(self, args: str) -> Dict[str, Any]:
        """解析 JSON 参数。"""
        import json
        try:
            return json.loads(args) if args else {}
        except json.JSONDecodeError:
            return {}

    def _json_dumps(self, obj: Any) -> str:
        """序列化为 JSON。"""
        import json
        return json.dumps(obj, ensure_ascii=False)


__all__ = ["BedrockTransport"]