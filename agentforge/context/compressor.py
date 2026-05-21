"""上下文压缩器。

实现上下文压缩策略，保护关键消息。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

from agentforge.types import Message
from agentforge.context.estimator import TokenEstimator

if TYPE_CHECKING:
    from agentforge.config import CompressionSettings

logger = logging.getLogger(__name__)


@dataclass
class ProtectionRegion:
    """保护区域。

    定义需要保护的消息范围。
    """

    start: int  # 开始索引
    end: int  # 结束索引（不包含）
    priority: int  # 优先级（越高越重要）


class ContextCompressor:
    """上下文压缩器。

    策略：
    - 保护头部消息（系统提示）
    - 保护尾部消息（最近对话）
    - 压缩中间消息

    使用示例：
        compressor = ContextCompressor(settings)

        # 检查是否需要压缩
        if compressor.should_compress(messages):
            compressed = compressor.compress(messages)
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
        self._max_tokens = getattr(settings, 'max_tokens', 100000) if settings else 100000
        self._protect_head = getattr(settings, 'protect_head', 3) if settings else 3
        self._protect_tail = getattr(settings, 'protect_tail', 5) if settings else 5
        self._compression_ratio = getattr(settings, 'compression_ratio', 0.5) if settings else 0.5

    def should_compress(self, messages: List[Message]) -> bool:
        """判断是否需要压缩。

        Args:
            messages: 消息列表

        Returns:
            True 如果需要压缩
        """
        current_tokens = self._estimator.estimate_messages(messages)
        return current_tokens > self._max_tokens

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

        # 保护尾部（最近对话）
        if self._protect_tail > 0 and len(messages) > self._protect_head:
            tail_start = max(len(messages) - self._protect_tail, self._protect_head)
            regions.append(ProtectionRegion(
                start=tail_start,
                end=len(messages),
                priority=8,
            ))

        return regions

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
        """压缩消息列表。

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

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
        summary_text = self._create_summary(messages, compressible_indices)

        # 构建新消息列表
        result = []

        # 添加头部保护消息
        for i in range(min(self._protect_head, len(messages))):
            result.append(messages[i])

        # 添加压缩摘要
        if summary_text:
            from agentforge.types import TextContent
            result.append(Message(
                role="assistant",
                content=[TextContent(text=f"[上下文摘要] {summary_text}")],
            ))

        # 添加尾部保护消息
        tail_start = max(len(messages) - self._protect_tail, self._protect_head)
        for i in range(tail_start, len(messages)):
            result.append(messages[i])

        return result

    def _create_summary(
        self,
        messages: List[Message],
        indices: List[int],
    ) -> str:
        """创建压缩摘要。

        Args:
            messages: 消息列表
            indices: 需要压缩的索引

        Returns:
            摘要文本
        """
        # 简化实现：提取关键信息
        summary_parts = []

        for i in indices:
            msg = messages[i]
            # 提取文本内容
            for content in msg.content:
                if hasattr(content, 'text') and content.text:
                    # 截取前 100 字符
                    text = content.text[:100]
                    if len(content.text) > 100:
                        text += "..."
                    summary_parts.append(f"{msg.role}: {text}")

        if not summary_parts:
            return ""

        # 合并摘要
        return "\n".join(summary_parts[:10])  # 最多 10 条

    def estimate_compressed_tokens(self, messages: List[Message]) -> int:
        """估算压缩后的 Token 数量。

        Args:
            messages: 消息列表

        Returns:
            估算的 Token 数量
        """
        compressed = self.compress(messages)
        return self._estimator.estimate_messages(compressed)