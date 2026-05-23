"""自动记忆提取器。

从对话中自动提取值得记忆的信息。
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from hai_agent.memory.metadata import MemoryMetadata, MemorySource, MemoryType
from hai_agent.types.errors import ProviderError

if TYPE_CHECKING:
    from hai_agent.types import NormalizedResponse

logger = logging.getLogger(__name__)


# 默认提取提示
DEFAULT_EXTRACTION_PROMPT = """分析以下对话，提取值得长期记忆的信息。

## 用户消息
{user_message}

## 助手回复
{assistant_response}

## 提取规则
1. 只提取重要的事实信息（用户姓名、偏好、约束等）
2. 不要提取临时性信息或具体任务细节
3. 每条记忆应该简洁明确

## 输出格式
如果值得记忆，输出 JSON 数组：
[{{"content": "记忆内容", "type": "fact|preference", "importance": 0.0-1.0}}]

如果不值得记忆，输出空数组：[]
"""


@dataclass
class ExtractedMemory:
    """提取的记忆条目。"""

    content: str
    memory_type: MemoryType
    importance: float
    confidence: float = 0.8

    def to_metadata(self) -> MemoryMetadata:
        """转换为元数据。"""
        return MemoryMetadata(
            source=MemorySource.AGENT,
            memory_type=self.memory_type,
            importance=self.importance,
            confidence=self.confidence,
        )


class MemoryExtractor(ABC):
    """记忆提取器抽象基类。"""

    @abstractmethod
    def extract(
        self,
        user_message: str,
        assistant_response: str,
    ) -> List[ExtractedMemory]:
        """从对话中提取记忆。

        Args:
            user_message: 用户消息
            assistant_response: 助手回复

        Returns:
            提取的记忆列表
        """
        ...


class RuleBasedExtractor(MemoryExtractor):
    """基于规则的记忆提取器。

    使用正则表达式和启发式规则提取记忆，无需 LLM 调用。
    """

    def __init__(self):
        """初始化规则提取器。"""
        # 名字模式（更严格，避免与职业模式冲突）
        self._name_patterns = [
            r"我叫(\w+)",
            r"我的名字是(\w+)",
            # 注意：移除 r"我是(\w+)" 因为会误匹配职业描述
        ]

        # 偏好模式（支持多词匹配）
        self._preference_patterns = [
            r"我喜欢使用\s+(\w+)",
            r"我喜欢\s+(\w+)",
            r"我偏好\s+(\w+)",
            r"我更喜欢\s+(\w+)",
            r"请(不要|别)(\w+)",
            r"总是(\w+)",
            r"永远(\w+)",
        ]

        # 技能/职业模式（支持多词匹配）
        self._role_patterns = [
            r"我是一名\s+(\w+\s+\w+)",  # 匹配 "Python 开发者"
            r"我是.*?(\w+工程师)",
            r"我是.*?(\w+开发者)",
            r"我的职业是\s+(\w+)",
        ]

    def extract(
        self,
        user_message: str,
        assistant_response: str,
    ) -> List[ExtractedMemory]:
        """从对话中提取记忆。"""
        memories = []

        # 提取名字
        for pattern in self._name_patterns:
            matches = re.findall(pattern, user_message)
            for match in matches:
                memories.append(ExtractedMemory(
                    content=f"用户名叫{match}",
                    memory_type=MemoryType.FACT,
                    importance=0.9,
                    confidence=0.95,
                ))

        # 提取偏好
        for pattern in self._preference_patterns:
            matches = re.findall(pattern, user_message)
            for match in matches:
                if isinstance(match, tuple):
                    preference = "".join(match)
                else:
                    preference = match
                memories.append(ExtractedMemory(
                    content=f"用户偏好：{preference}",
                    memory_type=MemoryType.PREFERENCE,
                    importance=0.8,
                    confidence=0.85,
                ))

        # 提取角色/职业
        for pattern in self._role_patterns:
            matches = re.findall(pattern, user_message)
            for match in matches:
                memories.append(ExtractedMemory(
                    content=f"用户是{match}",
                    memory_type=MemoryType.FACT,
                    importance=0.7,
                    confidence=0.9,
                ))

        return memories


class LLMExtractor(MemoryExtractor):
    """基于 LLM 的记忆提取器。

    使用 LLM 判断对话中是否包含值得记忆的信息。
    """

    def __init__(
        self,
        provider: "Provider",
        prompt_template: str = DEFAULT_EXTRACTION_PROMPT,
    ):
        """初始化 LLM 提取器。

        Args:
            provider: LLM Provider
            prompt_template: 提取提示模板
        """
        self._provider = provider
        self._prompt_template = prompt_template

    def extract(
        self,
        user_message: str,
        assistant_response: str,
    ) -> List[ExtractedMemory]:
        """使用 LLM 提取记忆。"""
        import json

        from hai_agent.types import Message, TextContent, NormalizedResponse

        prompt = self._prompt_template.format(
            user_message=user_message,
            assistant_response=assistant_response,
        )

        try:
            response: NormalizedResponse = self._provider.complete(
                messages=[Message(role="user", content=[TextContent(text=prompt)])],
                tools=None,
            )

            content = response.content or "[]"

            # 尝试解析 JSON
            # 处理可能的 markdown 代码块
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())

            memories = []
            for item in data:
                memory_type = MemoryType.FACT
                if item.get("type") == "preference":
                    memory_type = MemoryType.PREFERENCE

                memories.append(ExtractedMemory(
                    content=item.get("content", ""),
                    memory_type=memory_type,
                    importance=item.get("importance", 0.5),
                    confidence=0.8,
                ))

            return memories

        except (ProviderError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"LLM 记忆提取失败: {e}")
            return []


class HybridExtractor(MemoryExtractor):
    """混合提取器。

    先使用规则提取（快速），再使用 LLM 提取（精确）。
    """

    def __init__(
        self,
        provider: Optional["Provider"] = None,
        use_llm: bool = True,
    ):
        """初始化混合提取器。

        Args:
            provider: LLM Provider（可选）
            use_llm: 是否使用 LLM 辅助
        """
        self._rule_extractor = RuleBasedExtractor()
        self._llm_extractor = LLMExtractor(provider) if provider and use_llm else None

    def extract(
        self,
        user_message: str,
        assistant_response: str,
    ) -> List[ExtractedMemory]:
        """混合提取记忆。"""
        # 先用规则提取
        memories = self._rule_extractor.extract(user_message, assistant_response)

        # 如果规则没有提取到，尝试 LLM
        if not memories and self._llm_extractor:
            memories = self._llm_extractor.extract(user_message, assistant_response)

        return memories


# 提取器函数类型
ExtractorFunc = Callable[[str, str], List[ExtractedMemory]]


def create_extractor(
    provider: Optional["Provider"] = None,
    use_llm: bool = False,
) -> MemoryExtractor:
    """创建记忆提取器。

    Args:
        provider: LLM Provider（可选）
        use_llm: 是否使用 LLM 辅助

    Returns:
        记忆提取器实例
    """
    if use_llm and provider:
        return HybridExtractor(provider=provider, use_llm=True)
    return RuleBasedExtractor()


__all__ = [
    "ExtractedMemory",
    "MemoryExtractor",
    "RuleBasedExtractor",
    "LLMExtractor",
    "HybridExtractor",
    "create_extractor",
    "DEFAULT_EXTRACTION_PROMPT",
]
