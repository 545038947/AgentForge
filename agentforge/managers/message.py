"""消息管理器。

负责消息历史管理和上下文压缩触发。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, List, Optional

from agentforge.types import (
    Message,
    TextContent,
    ToolUseContent,
    ToolResultContent,
    ToolResult,
    NormalizedResponse,
)

if TYPE_CHECKING:
    from agentforge.config import Settings
    from agentforge.context import ContextCompressor
    from agentforge.memory import MemoryProvider

logger = logging.getLogger(__name__)


class MessageManager:
    """消息管理器，负责消息历史和上下文管理。

    职责：
    - 维护消息历史
    - 执行上下文压缩
    - 格式转换（Message <-> Provider 格式）

    不负责：
    - 消息内容解析（由 Provider/Transport 处理）
    - 工具执行（由 ToolOrchestrator 处理）

    使用示例：
        manager = MessageManager(settings)

        # 添加用户消息
        manager.add_user_message("你好")

        # 添加 assistant 响应
        manager.add_assistant_message(response)

        # 获取上下文
        context = manager.get_context()
    """

    def __init__(
        self,
        settings: "Settings",
        compressor: Optional["ContextCompressor"] = None,
        memory: Optional["MemoryProvider"] = None,
    ):
        """初始化消息管理器。

        Args:
            settings: 配置对象
            compressor: 上下文压缩器（可选）
            memory: 存储提供者（可选）
        """
        self._settings = settings
        self._messages: List[Message] = []
        self._compressor = compressor
        self._memory = memory

        # 系统提示组件
        self._system_prompt_parts: List[str] = []
        self._memory_context: Optional[str] = None
        self._skill_prompts: dict[str, str] = {}

    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示。

        Args:
            prompt: 系统提示文本
        """
        self._system_prompt_parts = [prompt] if prompt else []

    def add_system_prompt_part(self, part: str) -> None:
        """添加系统提示部分。

        Args:
            part: 提示部分
        """
        if part:
            self._system_prompt_parts.append(part)

    def add_memory_context(self, context: str) -> None:
        """添加记忆上下文。

        Args:
            context: 记忆上下文文本
        """
        self._memory_context = context

    def add_skill_prompt(self, skill_name: str, prompt: str) -> None:
        """添加技能提示。

        Args:
            skill_name: 技能名称
            prompt: 提示文本
        """
        self._skill_prompts[skill_name] = prompt

    def remove_skill_prompt(self, skill_name: str) -> None:
        """移除技能提示。

        Args:
            skill_name: 技能名称
        """
        self._skill_prompts.pop(skill_name, None)

    def get_system_prompt(self) -> Optional[str]:
        """获取完整的系统提示。

        Returns:
            系统提示文本
        """
        parts = list(self._system_prompt_parts)

        # 添加记忆上下文
        if self._memory_context:
            parts.append(f"\n## 记忆上下文\n{self._memory_context}")

        # 添加技能提示
        for skill_name, prompt in self._skill_prompts.items():
            parts.append(f"\n## 技能: {skill_name}\n{prompt}")

        return "\n".join(parts) if parts else None

    def add_message(self, message: Message) -> None:
        """添加消息到历史。

        Args:
            message: 消息对象
        """
        self._messages.append(message)

        # 持久化到存储
        if self._memory:
            try:
                self._memory.save(f"msg_{len(self._messages)}", message)
            except Exception as e:
                logger.warning(f"保存消息到存储失败: {e}")

    def add_user_message(self, content: str) -> Message:
        """添加用户消息。

        Args:
            content: 消息内容

        Returns:
            创建的消息对象
        """
        message = Message(
            role="user",
            content=[TextContent(text=content)],
        )
        self.add_message(message)
        return message

    def add_assistant_message(self, response: NormalizedResponse) -> Message:
        """添加 assistant 消息。

        Args:
            response: 标准化响应

        Returns:
            创建的消息对象
        """
        content = []

        # 添加文本内容
        if response.content:
            content.append(TextContent(text=response.content))

        # 添加工具调用
        if response.tool_calls:
            for tc in response.tool_calls:
                try:
                    args = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                content.append(ToolUseContent(
                    id=tc.id,
                    name=tc.name,
                    input=args,
                ))

        message = Message(role="assistant", content=content)
        self.add_message(message)
        return message

    def add_tool_results(self, results: List[ToolResult]) -> List[Message]:
        """添加工具结果消息。

        Args:
            results: 工具结果列表

        Returns:
            创建的消息对象列表
        """
        messages = []
        for result in results:
            message = Message(
                role="user",
                content=[ToolResultContent(
                    tool_use_id=result.tool_call_id,
                    content=result.content,
                    is_error=result.is_error,
                )],
            )
            self.add_message(message)
            messages.append(message)
        return messages

    def get_messages(self) -> List[Message]:
        """获取所有消息。

        Returns:
            消息列表
        """
        return self._messages.copy()

    def get_context(self) -> List[Message]:
        """获取当前上下文（可能压缩）。

        Returns:
            消息列表
        """
        if self._compressor:
            # 检查是否需要压缩
            if self._compressor.should_compress(self._messages):
                self._messages = self._compressor.compress(self._messages)

        return self._messages.copy()

    def clear(self) -> None:
        """清空消息历史。"""
        self._messages.clear()

    def __len__(self) -> int:
        """返回消息数量。"""
        return len(self._messages)

    def __iter__(self):
        """迭代消息。"""
        return iter(self._messages)
