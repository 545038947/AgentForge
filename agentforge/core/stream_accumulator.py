"""流式响应累积器。

处理流式响应的内容累积、工具调用累积、增量计算等。
参考 hermes-agent 的流式处理设计。

主要功能：
1. 内容增量计算（避免重复发射）
2. 工具调用累积（支持 Ollama 的 index 重用问题）
3. 推理内容累积
4. 工具调用状态追踪（开始、进行中、完成）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from agentforge.types import ToolCall, Usage

logger = logging.getLogger(__name__)


@dataclass
class ToolCallAccumulator:
    """工具调用累积器。

    处理流式响应中的工具调用增量累积。
    支持 Ollama 等 Provider 的 index 重用问题（同一个 index 用于不同的工具调用）。

    参考 hermes-agent agent/chat_completion_helpers.py 的 tool_calls_acc 实现。
    """

    # 累积的工具调用字典：slot_index -> {id, name, arguments, extra_content}
    calls: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    # 已通知的工具调用名称（用于状态事件）
    notified_names: Set[int] = field(default_factory=set)

    # Ollama index 重用追踪
    last_id_at_index: Dict[int, str] = field(default_factory=dict)
    active_slot_by_index: Dict[int, int] = field(default_factory=dict)

    def add_delta(self, tc_delta: Any) -> Optional[str]:
        """添加工具调用增量。

        Args:
            tc_delta: OpenAI 格式的工具调用增量对象

        Returns:
            如果工具名称刚刚确定，返回名称（用于发射工具开始事件）
        """
        # 获取原始 index
        raw_idx = getattr(tc_delta, "index", 0) or 0
        delta_id = getattr(tc_delta, "id", "") or ""

        # 处理 Ollama 的 index 重用问题
        if raw_idx not in self.active_slot_by_index:
            self.active_slot_by_index[raw_idx] = raw_idx

        # 如果同一个 raw_idx 出现了不同的 id，说明是新的工具调用
        if delta_id and raw_idx in self.last_id_at_index and delta_id != self.last_id_at_index[raw_idx]:
            new_slot = max(self.calls, default=-1) + 1
            self.active_slot_by_index[raw_idx] = new_slot

        if delta_id:
            self.last_id_at_index[raw_idx] = delta_id

        # 获取实际 slot
        slot = self.active_slot_by_index[raw_idx]

        # 初始化或更新工具调用
        if slot not in self.calls:
            self.calls[slot] = {
                "id": delta_id,
                "type": "function",
                "function": {"name": "", "arguments": ""},
                "extra_content": None,
            }

        entry = self.calls[slot]

        # 更新 id
        if delta_id:
            entry["id"] = delta_id

        # 更新 function
        func = getattr(tc_delta, "function", None)
        if func:
            # 名称使用赋值而非累积（OpenAI 规范）
            name = getattr(func, "name", "") or ""
            if name:
                entry["function"]["name"] = name

            # arguments 使用累积
            args = getattr(func, "arguments", "") or ""
            if args:
                entry["function"]["arguments"] += args

        # 处理 extra_content (Gemini 协议)
        extra = getattr(tc_delta, "extra_content", None)
        if extra is None and hasattr(tc_delta, "model_extra"):
            extra = (getattr(tc_delta, "model_extra", None) or {}).get("extra_content")
        if extra is not None:
            if hasattr(extra, "model_dump"):
                try:
                    extra = extra.model_dump()
                except Exception:
                    pass
            entry["extra_content"] = extra

        # 检查是否需要通知工具开始
        tool_name = entry["function"]["name"]
        if tool_name and slot not in self.notified_names:
            self.notified_names.add(slot)
            return tool_name

        return None

    def has_calls(self) -> bool:
        """检查是否有工具调用。"""
        return bool(self.calls)

    def get_tool_calls(self) -> List["ToolCall"]:
        """获取完整的工具调用列表。

        Returns:
            ToolCall 对象列表
        """
        from agentforge.types import ToolCall

        result = []
        for slot in sorted(self.calls):
            tc_data = self.calls[slot]
            arguments = tc_data["function"]["arguments"]
            tool_name = tc_data["function"]["name"] or "?"

            # 尝试修复损坏的 arguments JSON
            if arguments and arguments.strip():
                try:
                    json.loads(arguments)
                except json.JSONDecodeError:
                    # 尝试简单修复
                    repaired = self._repair_arguments(arguments, tool_name)
                    if repaired:
                        arguments = repaired

            result.append(ToolCall(
                id=tc_data["id"],
                name=tool_name,
                arguments=arguments,
                provider_data={"extra_content": tc_data.get("extra_content")} if tc_data.get("extra_content") else None,
            ))

        return result

    def _repair_arguments(self, arguments: str, tool_name: str) -> Optional[str]:
        """尝试修复损坏的 arguments JSON。

        Args:
            arguments: 原始 arguments 字符串
            tool_name: 工具名称（用于日志）

        Returns:
            修复后的 JSON 字符串，无法修复返回 None
        """
        # 简单修复尝试
        trimmed = arguments.strip()

        # 尝试闭合未闭合的括号
        open_braces = trimmed.count("{") - trimmed.count("}")
        open_brackets = trimmed.count("[") - trimmed.count("]")

        if open_braces > 0:
            trimmed += "}" * open_braces
        if open_brackets > 0:
            trimmed += "]" * open_brackets

        # 移除尾部逗号
        if trimmed.endswith(","):
            trimmed = trimmed[:-1]

        try:
            json.loads(trimmed)
            logger.debug(f"修复工具 {tool_name} 的 arguments JSON")
            return trimmed
        except json.JSONDecodeError:
            return None


@dataclass
class StreamAccumulator:
    """流式响应累积器。

    管理流式响应的内容、推理、工具调用、使用统计的累积。
    支持增量计算，避免重复发射已发送的内容。

    使用示例：
        accumulator = StreamAccumulator()
        for chunk in provider.stream(messages):
            # 处理文本增量
            content_delta = accumulator.add_content(chunk.content)
            if content_delta:
                yield StreamDelta(content=content_delta)

            # 处理推理增量
            reasoning_delta = accumulator.add_reasoning(chunk.reasoning)
            if reasoning_delta:
                yield StreamDelta(reasoning=reasoning_delta)

            # 处理工具调用增量
            new_tool_name = accumulator.add_tool_delta(chunk.tool_calls_delta)
            if new_tool_name:
                # 发射工具开始事件
                dispatch_event(TOOL_GENERATING, {"name": new_tool_name})

            # 更新使用统计
            accumulator.update_usage(chunk.usage)

            # 更新结束原因
            accumulator.update_finish_reason(chunk.finish_reason)

        # 获取最终结果
        final_response = accumulator.build_response()
    """

    # 累积的文本内容
    content: str = ""

    # 累积的推理内容
    reasoning: str = ""

    # 工具调用累积器
    tool_calls: ToolCallAccumulator = field(default_factory=ToolCallAccumulator)

    # 使用统计
    usage: Optional["Usage"] = None

    # 结束原因
    finish_reason: Optional[str] = None

    # 模型名称
    model: Optional[str] = None

    def add_content(self, new_content: Optional[str]) -> str:
        """添加文本内容，返回增量。

        Args:
            new_content: 新的内容（可能是完整内容或增量）

        Returns:
            增量内容（新发送的部分）
        """
        if not new_content:
            return ""

        # 判断是累积式还是增量式
        # OpenAI SDK 通常是累积式（每次返回完整内容）
        # 但某些 HTTP 直接调用可能是增量式
        if new_content.startswith(self.content):
            # 累积式：计算增量
            delta = new_content[len(self.content):]
            self.content = new_content
            return delta
        else:
            # 增量式：直接累积
            delta = new_content
            self.content += new_content
            return delta

    def add_reasoning(self, new_reasoning: Optional[str]) -> str:
        """添加推理内容，返回增量。

        Args:
            new_reasoning: 新的推理内容

        Returns:
            增量推理内容
        """
        if not new_reasoning:
            return ""

        if new_reasoning.startswith(self.reasoning):
            delta = new_reasoning[len(self.reasoning):]
            self.reasoning = new_reasoning
            return delta
        else:
            delta = new_reasoning
            self.reasoning += new_reasoning
            return delta

    def add_tool_delta(self, tc_deltas: Optional[List[Any]]) -> List[str]:
        """添加工具调用增量。

        Args:
            tc_deltas: 工具调用增量列表

        Returns:
            新确定的工具名称列表（用于发射工具开始事件）
        """
        if not tc_deltas:
            return []

        new_names = []
        for tc_delta in tc_deltas:
            name = self.tool_calls.add_delta(tc_delta)
            if name:
                new_names.append(name)

        return new_names

    def update_usage(self, usage: Optional["Usage"]) -> None:
        """更新使用统计。"""
        if usage:
            self.usage = usage

    def update_finish_reason(self, reason: Optional[str]) -> None:
        """更新结束原因。"""
        if reason:
            self.finish_reason = reason

    def update_model(self, model: Optional[str]) -> None:
        """更新模型名称。"""
        if model:
            self.model = model

    def should_suppress_text_streaming(self) -> bool:
        """检查是否应该抑制文本流式。

        当有工具调用时，通常抑制文本流式回调，
        避免 "我将使用工具..." 这类文本与工具调用一起显示。

        参考 hermes-agent: if not tool_calls_acc: _fire_stream_delta(...)
        """
        return self.tool_calls.has_calls()

    def has_content(self) -> bool:
        """检查是否有内容。"""
        return bool(self.content)

    def has_reasoning(self) -> bool:
        """检查是否有推理内容。"""
        return bool(self.reasoning)

    def has_tool_calls(self) -> bool:
        """检查是否有工具调用。"""
        return self.tool_calls.has_calls()

    def build_response(self) -> "NormalizedResponse":
        """构建最终响应。

        Returns:
            NormalizedResponse 对象
        """
        from agentforge.types import NormalizedResponse

        finish = self.finish_reason or "stop"
        if self.has_tool_calls():
            finish = "tool_calls"

        return NormalizedResponse(
            content=self.content or None,
            reasoning=self.reasoning or None,
            tool_calls=self.tool_calls.get_tool_calls() if self.has_tool_calls() else None,
            usage=self.usage,
            finish_reason=finish,
            model=self.model,
        )