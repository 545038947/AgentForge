"""响应类型定义。

定义 Provider 返回的标准化响应结构，支持跨 Provider 统一处理。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """标准化工具调用。

    从各 Provider 响应中提取的工具调用信息，统一格式便于后续处理。

    属性：
        id: 工具调用唯一标识（可能为 None，由 Agent 填充）
        name: 工具名称
        arguments: 工具参数（JSON 字符串格式）
        provider_data: Provider 特定元数据（可选）
    """
    id: Optional[str]
    name: str
    arguments: str  # JSON 字符串
    provider_data: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @property
    def parsed_arguments(self) -> Dict[str, Any]:
        """解析 arguments JSON 字符串为字典。"""
        if not self.arguments:
            return {}
        return json.loads(self.arguments)

    # ── 向后兼容属性 ──────────────────────────────────
    # 支持 tc.function.name / tc.function.arguments 访问模式

    @property
    def type(self) -> str:
        """返回 'function' 用于兼容 OpenAI 格式。"""
        return "function"

    @property
    def function(self) -> ToolCall:
        """返回自身，支持 tc.function.name 访问模式。"""
        return self

    @property
    def call_id(self) -> Optional[str]:
        """从 provider_data 获取 call_id（Codex 协议）。"""
        return (self.provider_data or {}).get("call_id")

    @property
    def response_item_id(self) -> Optional[str]:
        """从 provider_data 获取 response_item_id（Codex 协议）。"""
        return (self.provider_data or {}).get("response_item_id")

    @property
    def extra_content(self) -> Optional[Dict[str, Any]]:
        """从 provider_data 获取 extra_content（Gemini 协议）。"""
        return (self.provider_data or {}).get("extra_content")


@dataclass
class Usage:
    """Token 使用统计。"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0  # 缓存命中 Token 数

    @property
    def cache_hit_ratio(self) -> float:
        """缓存命中率。"""
        if self.prompt_tokens == 0:
            return 0.0
        return self.cached_tokens / self.prompt_tokens


@dataclass
class StreamDelta:
    """流式响应增量。

    表示流式响应中的单个增量块，包含文本增量、工具调用增量等。

    属性：
        content: 文本增量（可能为空字符串）
        reasoning: 推理增量（支持推理模型）
        tool_calls: 工具调用增量（流式工具调用）
        finish_reason: 结束原因（仅最后一个块有值）
        usage: Token 使用统计（仅最后一个块有值）
    """

    content: str = ""
    reasoning: str = ""
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None

    @property
    def has_content(self) -> bool:
        """检查是否有文本内容。"""
        return bool(self.content)

    @property
    def has_reasoning(self) -> bool:
        """检查是否有推理内容。"""
        return bool(self.reasoning)

    @property
    def has_tool_calls(self) -> bool:
        """检查是否有工具调用。"""
        return bool(self.tool_calls)

    @property
    def is_final(self) -> bool:
        """检查是否为最终块。"""
        return self.finish_reason is not None

    def __repr__(self) -> str:
        parts = []
        if self.content:
            parts.append(f"content={self.content!r}")
        if self.reasoning:
            parts.append(f"reasoning={self.reasoning!r}")
        if self.tool_calls:
            parts.append(f"tool_calls={len(self.tool_calls)}")
        if self.finish_reason:
            parts.append(f"finish_reason={self.finish_reason!r}")
        return f"StreamDelta({', '.join(parts)})"


@dataclass
class NormalizedResponse:
    """标准化 API 响应。

    所有 Provider 返回的响应统一为此格式，便于 Agent 统一处理。

    属性：
        content: 文本内容（可能为 None）
        tool_calls: 工具调用列表（可能为 None）
        finish_reason: 结束原因（"stop", "tool_calls", "length", "content_filter"）
        reasoning: 推理内容（支持推理模型的 Provider）
        usage: Token 使用统计
        provider_data: Provider 特定元数据
        id: 响应唯一标识
        model: 实际使用的模型名称
        created: 响应创建时间戳
    """
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"  # "stop", "tool_calls", "length", "content_filter"
    reasoning: Optional[str] = None
    usage: Optional[Usage] = None
    provider_data: Optional[Dict[str, Any]] = field(default=None, repr=False)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model: Optional[str] = None
    created: int = field(default_factory=lambda: int(__import__("time").time()))

    # ── 向后兼容属性 ──────────────────────────────────

    @property
    def reasoning_content(self) -> Optional[str]:
        """从 provider_data 获取 reasoning_content。"""
        return (self.provider_data or {}).get("reasoning_content")

    @property
    def reasoning_details(self) -> Optional[List[Any]]:
        """从 provider_data 获取 reasoning_details（Anthropic 协议）。"""
        return (self.provider_data or {}).get("reasoning_details")

    @property
    def codex_reasoning_items(self) -> Optional[List[Any]]:
        """从 provider_data 获取 codex_reasoning_items。"""
        return (self.provider_data or {}).get("codex_reasoning_items")

    @property
    def codex_message_items(self) -> Optional[List[Any]]:
        """从 provider_data 获取 codex_message_items。"""
        return (self.provider_data or {}).get("codex_message_items")

    @property
    def has_tool_calls(self) -> bool:
        """检查是否包含工具调用。"""
        return bool(self.tool_calls)

    @property
    def is_stopped(self) -> bool:
        """检查是否正常结束。"""
        return self.finish_reason == "stop"

    @property
    def is_length_limited(self) -> bool:
        """检查是否因长度限制结束。"""
        return self.finish_reason == "length"

    @property
    def is_content_filtered(self) -> bool:
        """检查是否因内容过滤结束。"""
        return self.finish_reason == "content_filter"


# ── 工厂函数 ──────────────────────────────────────────

def build_tool_call(
    id: Optional[str],
    name: str,
    arguments: Any,
    **provider_fields: Any,
) -> ToolCall:
    """构建 ToolCall，自动序列化 arguments。

    参数：
        id: 工具调用 ID
        name: 工具名称
        arguments: 工具参数（dict 会自动转为 JSON 字符串）
        **provider_fields: Provider 特定字段，收集到 provider_data

    返回：
        ToolCall 实例
    """
    args_str = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments)
    provider_data = dict(provider_fields) if provider_fields else None
    return ToolCall(id=id, name=name, arguments=args_str, provider_data=provider_data)


def map_finish_reason(reason: Optional[str], mapping: Dict[str, str]) -> str:
    """映射 Provider 特定的结束原因到标准值。

    参数：
        reason: Provider 返回的结束原因
        mapping: Provider 到标准值的映射字典

    返回：
        标准化的结束原因
    """
    if reason is None:
        return "stop"
    return mapping.get(reason, "stop")