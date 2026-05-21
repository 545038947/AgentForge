"""委托工具。

提供任务委托功能。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from agentforge.tools.base import Tool
from agentforge.types import ToolResult

logger = logging.getLogger(__name__)


class DelegateTool(Tool):
    """委托工具。

    将任务委托给子 Agent 执行。

    使用示例：
        tool = DelegateTool(delegation_manager)

        result = tool.execute(
            tool_call_id="call-1",
            goal="搜索相关文档",
            context="项目背景",
        )
    """

    # 工具元信息
    timeout: float = 600.0
    requires_approval: bool = False
    dangerous: bool = False

    def __init__(self, delegation_manager=None):
        """初始化委托工具。

        Args:
            delegation_manager: DelegationManager 实例
        """
        self._delegation_manager = delegation_manager

    @property
    def name(self) -> str:
        return "delegate_task"

    @property
    def description(self) -> str:
        return """将任务委托给子 Agent 执行。

适用于：
- 需要并行处理的独立任务
- 复杂任务的分解
- 需要隔离执行的任务

参数：
- goal: 任务目标（必需）
- context: 任务上下文（可选）
- toolsets: 工具集列表（可选）
- role: 角色（leaf 或 orchestrator，默认 leaf）
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "任务目标",
                },
                "context": {
                    "type": "string",
                    "description": "任务上下文",
                },
                "toolsets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "工具集列表",
                },
                "role": {
                    "type": "string",
                    "enum": ["leaf", "orchestrator"],
                    "description": "子 Agent 角色",
                },
            },
            "required": ["goal"],
        }

    def execute(
        self,
        tool_call_id: str,
        goal: str,
        context: Optional[str] = None,
        toolsets: Optional[List[str]] = None,
        role: str = "leaf",
        **kwargs,
    ) -> ToolResult:
        """执行委托。

        Args:
            tool_call_id: 工具调用 ID
            goal: 任务目标
            context: 任务上下文
            toolsets: 工具集列表
            role: 角色

        Returns:
            工具执行结果
        """
        if self._delegation_manager is None:
            return ToolResult(
                tool_call_id=tool_call_id,
                content="错误：委托管理器未配置",
                is_error=True,
            )

        try:
            result = self._delegation_manager.delegate(
                goal=goal,
                context=context,
                toolsets=toolsets,
                role=role,
            )

            # 格式化结果
            summary = result.get_summary()
            if result.is_success():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"委托成功：\n{summary}",
                )
            else:
                errors = [r.error for r in result.results if r.error]
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"委托失败：{'; '.join(errors)}",
                    is_error=True,
                )

        except Exception as e:
            logger.error(f"委托执行错误: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"委托执行错误: {e}",
                is_error=True,
            )