"""上下文压缩器。

实现上下文压缩策略，保护关键消息。
支持 LLM 辅助摘要生成和迭代式摘要更新。
参考 hermes-agent/agent/context_compressor.py。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

from hai_agent.types import Message, TextContent, ToolUseContent, ToolResultContent
from hai_agent.types.errors import ProviderError
from hai_agent.context.estimator import TokenEstimator

if TYPE_CHECKING:
    from hai_agent.config import CompressionSettings
    from hai_agent.providers import Provider

logger = logging.getLogger(__name__)


@dataclass
class ProtectionRegion:
    """保护区域。

    定义需要保护的消息范围。
    """

    start: int  # 开始索引
    end: int  # 结束索引（不包含）
    priority: int  # 优先级（越高越重要）


# 结构化摘要模板
SUMMARY_TEMPLATE = """## 活动任务
{active_task}

## 目标
{goal}

## 约束与偏好
{constraints}

## 已完成操作
{completed_actions}

## 进行中
{in_progress}

## 关键决策
{key_decisions}

## 待处理事项
{pending_items}

## 相关上下文
{relevant_context}
"""

# LLM 摘要提示模板
LLM_SUMMARY_PROMPT = """你是一个专业的对话摘要助手。请将以下对话历史压缩为一个结构化摘要。

## 要求
1. 保留关键信息和决策
2. 记录用户偏好和约束
3. 跟踪任务进度
4. 使用简洁的语言

## 之前的摘要
{previous_summary}

## 新增对话
{new_messages}

## 输出格式
请使用以下 Markdown 格式输出摘要：

## 活动任务
（当前正在进行的任务）

## 目标
（用户的目标）

## 约束与偏好
（用户的偏好、约束条件）

## 已完成操作
（已完成的操作列表）

## 进行中
（正在进行的操作）

## 关键决策
（做出的关键决策）

## 待处理事项
（待处理的用户请求）

## 相关上下文
（其他重要上下文信息）
"""


class ContextCompressor:
    """上下文压缩器。

    策略：
    - 保护头部消息（系统提示）
    - 保护尾部消息（最近对话）
    - 压缩中间消息（LLM 辅助摘要）
    - 工具结果修剪

    使用示例：
        compressor = ContextCompressor(settings)

        # 检查是否需要压缩
        if compressor.should_compress(messages):
            # 简单压缩（基于规则）
            compressed = compressor.compress(messages)

            # LLM 辅助压缩
            compressed = compressor.compress_with_llm(messages, provider)
    """

    def __init__(
        self,
        settings: Optional["CompressionSettings"] = None,
        estimator: Optional[TokenEstimator] = None,
    ):
        """初始化压缩器。

        Args:
            settings: 压缩配置
            estimator: Token 估算器
        """
        self._settings = settings
        self._estimator = estimator or TokenEstimator()

        # 默认配置
        self._max_tokens = getattr(settings, "max_tokens", 100000) if settings else 100000
        self._protect_head = getattr(settings, "protect_head", 3) if settings else 3
        self._protect_tail = getattr(settings, "protect_tail", 6) if settings else 6
        self._threshold_percent = getattr(settings, "threshold_percent", 0.75) if settings else 0.75
        self._summary_target_ratio = getattr(settings, "summary_target_ratio", 0.20) if settings else 0.20

        # 迭代式摘要存储
        self._previous_summary: str = ""

    def should_compress(self, messages: List[Message]) -> bool:
        """判断是否需要压缩。

        Args:
            messages: 消息列表

        Returns:
            True 如果需要压缩
        """
        current_tokens = self._estimator.estimate_messages(messages)
        threshold = int(self._max_tokens * self._threshold_percent)
        return current_tokens > threshold

    def get_protection_regions(self, messages: List[Message]) -> List[ProtectionRegion]:
        """计算保护区域。

        Args:
            messages: 消息列表

        Returns:
            保护区域列表
        """
        regions = []

        # 保护头部（系统提示等）
        if self._protect_head > 0 and len(messages) > 0:
            head_end = min(self._protect_head, len(messages))
            regions.append(ProtectionRegion(
                start=0,
                end=head_end,
                priority=10,
            ))

        # 保护尾部（最近对话）- 基于 Token 预算
        if self._protect_tail > 0 and len(messages) > self._protect_head:
            # 计算尾部保护边界
            tail_start = self._find_tail_boundary(messages)
            regions.append(ProtectionRegion(
                start=tail_start,
                end=len(messages),
                priority=8,
            ))

        return regions

    def _find_tail_boundary(self, messages: List[Message]) -> int:
        """查找尾部保护边界。

        基于 Token 预算而非消息数量。

        Args:
            messages: 消息列表

        Returns:
            尾部保护的起始索引
        """
        # 计算尾部 Token 预算（约占总预算的 30%）
        tail_budget = int(self._max_tokens * 0.3)
        soft_ceiling = int(tail_budget * 0.8)

        # 从尾部向前累积
        accumulated = 0
        head_end = min(self._protect_head, len(messages))

        for i in range(len(messages) - 1, head_end - 1, -1):
            msg_tokens = self._estimator.estimate_message(messages[i])
            accumulated += msg_tokens

            if accumulated > soft_ceiling:
                # 对齐工具对（避免在工具组中间切割）
                return self._align_boundary_backward(messages, i + 1)

        return head_end

    def _align_boundary_backward(self, messages: List[Message], index: int) -> int:
        """向后对齐边界（避免在工具组中间切割）。

        Args:
            messages: 消息列表
            index: 当前边界索引

        Returns:
            对齐后的边界索引
        """
        # 检查 index-1 是否是工具调用消息
        if index < len(messages):
            msg = messages[index]
            if self._has_tool_use(msg):
                # 找到对应的工具结果
                tool_ids = self._get_tool_ids(msg)
                for i in range(index + 1, min(index + 5, len(messages))):
                    if self._has_tool_result_for(messages[i], tool_ids):
                        # 对齐到工具结果之后
                        return i + 1

        return index

    def _has_tool_use(self, message: Message) -> bool:
        """检查消息是否包含工具调用。"""
        for content in message.content:
            if isinstance(content, ToolUseContent):
                return True
        return False

    def _get_tool_ids(self, message: Message) -> List[str]:
        """获取消息中的工具调用 ID。"""
        ids = []
        for content in message.content:
            if isinstance(content, ToolUseContent):
                ids.append(content.id)
        return ids

    def _has_tool_result_for(self, message: Message, tool_ids: List[str]) -> bool:
        """检查消息是否包含指定工具的结果。"""
        for content in message.content:
            if isinstance(content, ToolResultContent):
                if content.tool_use_id in tool_ids:
                    return True
        return False

    def is_protected(self, index: int, regions: List[ProtectionRegion]) -> bool:
        """检查索引是否在保护区域内。

        Args:
            index: 消息索引
            regions: 保护区域列表

        Returns:
            True 如果在保护区域内
        """
        for region in regions:
            if region.start <= index < region.end:
                return True
        return False

    def compress(self, messages: List[Message]) -> List[Message]:
        """压缩消息列表（基于规则的简单压缩）。

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        # 修剪工具结果
        messages = self._trim_tool_results(messages)

        # 修复孤立的工具对
        messages = self._sanitize_tool_pairs(messages)

        # 计算保护区域
        regions = self.get_protection_regions(messages)

        # 收集需要压缩的消息
        compressible_indices = []
        for i, msg in enumerate(messages):
            if not self.is_protected(i, regions):
                compressible_indices.append(i)

        if not compressible_indices:
            # 没有可压缩的消息
            return messages

        # 创建压缩摘要消息
        summary_text = self._create_simple_summary(messages, compressible_indices)

        # 构建新消息列表
        result = []

        # 添加头部保护消息
        head_end = min(self._protect_head, len(messages))
        for i in range(head_end):
            result.append(messages[i])

        # 添加压缩摘要
        if summary_text:
            result.append(Message(
                role="assistant",
                content=[TextContent(text=f"[上下文摘要]\n{summary_text}")],
            ))

        # 添加尾部保护消息
        tail_start = self._find_tail_boundary(messages)
        for i in range(tail_start, len(messages)):
            result.append(messages[i])

        return result

    def compress_with_llm(
        self,
        messages: List[Message],
        provider: "Provider",
        max_summary_tokens: int = 1000,
    ) -> List[Message]:
        """使用 LLM 辅助压缩消息列表。

        Args:
            messages: 消息列表
            provider: LLM Provider
            max_summary_tokens: 摘要最大 Token 数

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        # 修剪工具结果
        messages = self._trim_tool_results(messages)

        # 修复孤立的工具对
        messages = self._sanitize_tool_pairs(messages)

        # 计算保护区域
        regions = self.get_protection_regions(messages)

        # 收集需要压缩的消息
        compressible_indices = []
        for i, msg in enumerate(messages):
            if not self.is_protected(i, regions):
                compressible_indices.append(i)

        if not compressible_indices:
            return messages

        # 生成 LLM 摘要
        summary_text = self._generate_llm_summary(
            messages,
            compressible_indices,
            provider,
            max_summary_tokens,
        )

        # 构建新消息列表
        result = []

        # 添加头部保护消息
        head_end = min(self._protect_head, len(messages))
        for i in range(head_end):
            result.append(messages[i])

        # 添加压缩摘要
        if summary_text:
            # 保存摘要供下次迭代使用
            self._previous_summary = summary_text
            result.append(Message(
                role="assistant",
                content=[TextContent(text=f"[上下文摘要]\n{summary_text}")],
            ))

        # 添加尾部保护消息
        tail_start = self._find_tail_boundary(messages)
        for i in range(tail_start, len(messages)):
            result.append(messages[i])

        return result

    def _trim_tool_results(self, messages: List[Message]) -> List[Message]:
        """修剪工具结果（去重、截断大输出）。

        Args:
            messages: 消息列表

        Returns:
            修剪后的消息列表
        """
        result = []
        seen_tool_results: dict = {}  # tool_use_id -> result_hash

        for msg in messages:
            new_content = []
            for content in msg.content:
                if isinstance(content, ToolResultContent):
                    # 检查是否重复
                    result_hash = hash(content.content[:200]) if content.content else 0
                    key = content.tool_use_id

                    if key in seen_tool_results:
                        old_hash = seen_tool_results[key]
                        if old_hash == result_hash:
                            # 重复结果，替换为简短提示
                            new_content.append(ToolResultContent(
                                tool_use_id=key,
                                content=f"[重复结果: {content.content[:50]}...]" if content.content else "[空结果]",
                            ))
                            continue

                    seen_tool_results[key] = result_hash

                    # 截断大输出
                    if content.content and len(content.content) > 2000:
                        new_content.append(ToolResultContent(
                            tool_use_id=key,
                            content=content.content[:2000] + "\n...[已截断]",
                        ))
                        continue

                new_content.append(content)

            if new_content:
                result.append(Message(role=msg.role, content=new_content))

        return result

    def _sanitize_tool_pairs(self, messages: List[Message]) -> List[Message]:
        """修复孤立的工具对（tool_call 没有 tool_result 或反之）。

        Args:
            messages: 消息列表

        Returns:
            修复后的消息列表
        """
        # 收集所有 tool_use_id
        tool_use_ids = set()
        for msg in messages:
            for content in msg.content:
                if isinstance(content, ToolUseContent):
                    tool_use_ids.add(content.id)

        # 收集所有 tool_result_id
        tool_result_ids = set()
        for msg in messages:
            for content in msg.content:
                if isinstance(content, ToolResultContent):
                    tool_result_ids.add(content.tool_use_id)

        # 找出孤立的
        orphan_calls = tool_use_ids - tool_result_ids
        orphan_results = tool_result_ids - tool_use_ids

        if not orphan_calls and not orphan_results:
            return messages

        # 修复：移除孤立的结果，为孤立的调用添加占位结果
        result = []
        for msg in messages:
            new_content = []
            for content in msg.content:
                if isinstance(content, ToolResultContent):
                    if content.tool_use_id in orphan_results:
                        # 跳过孤立的结果
                        continue
                new_content.append(content)

            if new_content:
                result.append(Message(role=msg.role, content=new_content))

        # 为孤立的调用添加占位结果
        for call_id in orphan_calls:
            result.append(Message(
                role="user",
                content=[ToolResultContent(
                    tool_use_id=call_id,
                    content="[工具结果未记录]",
                )],
            ))

        return result

    def _create_simple_summary(
        self,
        messages: List[Message],
        indices: List[int],
    ) -> str:
        """创建简单摘要（基于规则）。

        Args:
            messages: 消息列表
            indices: 需要压缩的索引

        Returns:
            摘要文本
        """
        summary_parts = []

        for i in indices:
            msg = messages[i]
            # 提取文本内容
            for content in msg.content:
                if hasattr(content, "text") and content.text:
                    # 截取前 100 字符
                    text = content.text[:100]
                    if len(content.text) > 100:
                        text += "..."
                    summary_parts.append(f"{msg.role}: {text}")

        if not summary_parts:
            return ""

        # 合并摘要
        return "\n".join(summary_parts[:10])  # 最多 10 条

    def _generate_llm_summary(
        self,
        messages: List[Message],
        indices: List[int],
        provider: "Provider",
        max_tokens: int,
    ) -> str:
        """使用 LLM 生成摘要。

        Args:
            messages: 消息列表
            indices: 需要压缩的索引
            provider: LLM Provider
            max_tokens: 最大 Token 数

        Returns:
            摘要文本
        """
        # 构建消息文本
        messages_text = []
        for i in indices:
            msg = messages[i]
            for content in msg.content:
                if hasattr(content, "text") and content.text:
                    messages_text.append(f"[{msg.role}]: {content.text}")

        if not messages_text:
            return ""

        # 构建提示
        prompt = LLM_SUMMARY_PROMPT.format(
            previous_summary=self._previous_summary or "(无)",
            new_messages="\n".join(messages_text),
        )

        try:
            # 调用 LLM
            from hai_agent.types import NormalizedResponse

            response: NormalizedResponse = provider.complete(
                messages=[Message(role="user", content=[TextContent(text=prompt)])],
                tools=None,
            )

            return response.content or ""

        except (ProviderError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"LLM 摘要生成失败: {e}")
            # 回退到简单摘要
            return self._create_simple_summary(messages, indices)

    def estimate_compressed_tokens(self, messages: List[Message]) -> int:
        """估算压缩后的 Token 数量。

        Args:
            messages: 消息列表

        Returns:
            估算的 Token 数量
        """
        compressed = self.compress(messages)
        return self._estimator.estimate_messages(compressed)

    def reset_summary(self) -> None:
        """重置迭代式摘要。"""
        self._previous_summary = ""

    def get_previous_summary(self) -> str:
        """获取之前的摘要（用于调试）。"""
        return self._previous_summary


__all__ = [
    "ContextCompressor",
    "ProtectionRegion",
    "SUMMARY_TEMPLATE",
    "LLM_SUMMARY_PROMPT",
]