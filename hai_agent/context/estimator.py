"""Token 估算器。

估算消息的 Token 数量。
"""

from __future__ import annotations

import logging
import re
from typing import List

from hai_agent.types import Message, TextContent, ImageContent, ToolUseContent, ToolResultContent

logger = logging.getLogger(__name__)


class TokenEstimator:
    """Token 估算器。

    提供多种估算策略：
    - 字符计数法（简单快速）
    - 分词法（更精确）

    使用示例：
        estimator = TokenEstimator()

        # 估算单条消息
        tokens = estimator.estimate_message(message)

        # 估算消息列表
        total = estimator.estimate_messages(messages)
    """

    # 不同语言的字符/Token 比率
    # 中文约 1.5-2 字符/Token，英文约 4 字符/Token
    CHARS_PER_TOKEN_CN = 1.5
    CHARS_PER_TOKEN_EN = 4.0

    # 工具调用的额外 Token 开销
    TOOL_CALL_OVERHEAD = 20

    # 图片 Token 估算（固定值，简化处理）
    IMAGE_TOKEN_LOW = 85  # 低分辨率
    IMAGE_TOKEN_HIGH = 170  # 高分辨率

    def __init__(
        self,
        chars_per_token: float = None,
        use_smart_estimate: bool = True,
    ):
        """初始化 Token 估算器。

        Args:
            chars_per_token: 自定义字符/Token 比率（可选）
            use_smart_estimate: 是否使用智能估算（区分中英文）
        """
        self._chars_per_token = chars_per_token
        self._use_smart_estimate = use_smart_estimate

    def estimate_text(self, text: str) -> int:
        """估算文本的 Token 数量。

        Args:
            text: 文本内容

        Returns:
            估算的 Token 数量
        """
        if not text:
            return 0

        if self._chars_per_token:
            return int(len(text) / self._chars_per_token)

        if self._use_smart_estimate:
            # 智能估算：区分中英文
            cn_chars = len(re.findall(r'[一-鿿]', text))
            en_chars = len(text) - cn_chars

            cn_tokens = cn_chars / self.CHARS_PER_TOKEN_CN
            en_tokens = en_chars / self.CHARS_PER_TOKEN_EN

            return int(cn_tokens + en_tokens)

        # 默认使用英文比率
        return int(len(text) / self.CHARS_PER_TOKEN_EN)

    def estimate_content_block(self, content) -> int:
        """估算内容块的 Token 数量。

        Args:
            content: 内容块（TextContent、ImageContent 等）

        Returns:
            估算的 Token 数量
        """
        if isinstance(content, TextContent):
            return self.estimate_text(content.text)

        elif isinstance(content, ImageContent):
            # 图片 Token 估算
            if content.detail == "low":
                return self.IMAGE_TOKEN_LOW
            else:
                return self.IMAGE_TOKEN_HIGH

        elif isinstance(content, ToolUseContent):
            # 工具调用：名称 + 参数 + 开销
            tokens = self.estimate_text(content.name)
            if content.input:
                import json
                args_str = json.dumps(content.input, ensure_ascii=False)
                tokens += self.estimate_text(args_str)
            return tokens + self.TOOL_CALL_OVERHEAD

        elif isinstance(content, ToolResultContent):
            # 工具结果：内容 + 开销
            tokens = self.estimate_text(content.content)
            return tokens + self.TOOL_CALL_OVERHEAD

        else:
            # 未知类型，使用字符串估算
            return self.estimate_text(str(content))

    def estimate_message(self, message: Message) -> int:
        """估算单条消息的 Token 数量。

        Args:
            message: 消息对象

        Returns:
            估算的 Token 数量
        """
        tokens = 0

        # 角色 Token（约 4 个）
        tokens += 4

        # 内容 Token
        for content in message.content:
            tokens += self.estimate_content_block(content)

        return tokens

    def estimate_messages(self, messages: List[Message]) -> int:
        """估算消息列表的 Token 数量。

        Args:
            messages: 消息列表

        Returns:
            估算的总 Token 数量
        """
        total = 0
        for message in messages:
            total += self.estimate_message(message)

        # 消息格式开销（每条消息约 4 个 Token）
        total += len(messages) * 4

        return total