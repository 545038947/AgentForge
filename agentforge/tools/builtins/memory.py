"""记忆工具。

提供记忆存储和查询功能，让 LLM 可以主动保存和检索重要信息。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from agentforge.tools.base import Tool
from agentforge.types import ToolResult

if TYPE_CHECKING:
    from agentforge.memory import MemoryManager

logger = logging.getLogger(__name__)


class SaveMemoryTool(Tool):
    """保存记忆工具。

    让 LLM 可以主动保存重要信息到长期记忆存储。
    """

    # 工具元信息
    timeout: float = 10.0
    requires_approval: bool = False
    dangerous: bool = False

    def __init__(self, memory_manager: "MemoryManager"):
        """初始化记忆工具。

        Args:
            memory_manager: 记忆管理器实例
        """
        self._memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "save_memory"

    @property
    def description(self) -> str:
        return """保存重要信息到长期记忆。

当你需要记住用户告诉你的重要信息时使用此工具，例如：
- 用户的个人信息（姓名、职业、偏好等）
- 用户明确要求你记住的内容
- 对后续对话有帮助的关键信息

参数：
- content: 要保存的记忆内容（必需）
- memory_type: 记忆类型，"fact" 表示事实，"preference" 表示偏好（可选，默认 "fact"）
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要保存的记忆内容，应简洁明确",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["fact", "preference"],
                    "description": "记忆类型：fact=事实信息，preference=用户偏好",
                    "default": "fact",
                },
            },
            "required": ["content"],
        }

    def execute(
        self,
        tool_call_id: str,
        content: str,
        memory_type: str = "fact",
        **kwargs,
    ) -> ToolResult:
        """保存记忆。

        Args:
            tool_call_id: 工具调用 ID
            content: 记忆内容
            memory_type: 记忆类型

        Returns:
            工具执行结果
        """
        try:
            # 确定 target
            target = "memory" if memory_type == "fact" else "user"

            # 添加记忆（使用正确的方法名）
            success = self._memory_manager.add_memory_entry(target, content, sync=True)

            if success:
                logger.info(f"已保存记忆 [{memory_type}]: {content[:50]}...")
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"✅ 已保存记忆: {content}",
                )
            else:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content="⚠️ 保存记忆失败，请稍后重试",
                    is_error=True,
                )

        except (OSError, IOError, ValueError) as e:
            logger.error(f"保存记忆失败: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"保存记忆出错: {e}",
                is_error=True,
            )


class QueryMemoryTool(Tool):
    """查询记忆工具。

    让 LLM 可以查询已保存的记忆信息。
    """

    # 工具元信息
    timeout: float = 10.0
    requires_approval: bool = False
    dangerous: bool = False

    def __init__(self, memory_manager: "MemoryManager"):
        """初始化查询工具。

        Args:
            memory_manager: 记忆管理器实例
        """
        self._memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "query_memory"

    @property
    def description(self) -> str:
        return """查询已保存的记忆信息。

当你需要回忆之前保存的信息时使用此工具，例如：
- 查询用户的姓名、职业等信息
- 查询用户的偏好设置
- 回顾用户之前告诉你的重要内容

参数：
- query: 查询关键词（可选）
- memory_type: 查询类型，"all"=全部，"fact"=事实，"preference"=偏好（可选，默认 "all"）
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "查询关键词，用于筛选相关记忆",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["all", "fact", "preference"],
                    "description": "查询类型",
                    "default": "all",
                },
            },
            "required": [],
        }

    def execute(
        self,
        tool_call_id: str,
        query: Optional[str] = None,
        memory_type: str = "all",
        **kwargs,
    ) -> ToolResult:
        """查询记忆。

        Args:
            tool_call_id: 工具调用 ID
            query: 查询关键词
            memory_type: 查询类型

        Returns:
            工具执行结果
        """
        try:
            results: List[str] = []

            # 获取 MemoryStore
            if not self._memory_manager.has_memory_store():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content="记忆存储未启用",
                )

            memory_store = self._memory_manager._memory_store

            # 获取事实记忆
            if memory_type in ("all", "fact"):
                memory_entries = memory_store.memory_entries
                if query:
                    memory_entries = [e for e in memory_entries if query.lower() in e.lower()]
                results.extend(f"[事实] {e}" for e in memory_entries)

            # 获取偏好记忆
            if memory_type in ("all", "preference"):
                user_entries = memory_store.user_entries
                if query:
                    user_entries = [e for e in user_entries if query.lower() in e.lower()]
                results.extend(f"[偏好] {e}" for e in user_entries)

            if not results:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content="没有找到相关记忆",
                )

            return ToolResult(
                tool_call_id=tool_call_id,
                content="已保存的记忆：\n" + "\n".join(f"- {r}" for r in results),
            )

        except (OSError, ValueError) as e:
            logger.error(f"查询记忆失败: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"查询记忆出错: {e}",
                is_error=True,
            )
