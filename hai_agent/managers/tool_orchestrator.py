"""工具编排器。

负责工具执行的并发控制和审批流程。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from hai_agent.tools import Tool, ToolExecutor, ApprovalCallback, ApprovalManager
from hai_agent.types import ToolCall, ToolResult

if TYPE_CHECKING:
    from hai_agent.config import Settings
    from hai_agent.interrupt import InterruptToken

logger = logging.getLogger(__name__)


class ToolOrchestrator:
    """工具编排器，负责工具执行的并发控制。

    职责：
    - 管理工具执行器生命周期
    - 编排并发工具调用
    - 处理审批流程

    不负责：
    - 工具具体实现（由 Tool 类处理）
    - 消息历史（由 MessageManager 处理）

    使用示例：
        orchestrator = ToolOrchestrator(settings, approval_callback)

        # 执行工具调用
        results = orchestrator.execute(
            tool_calls=response.tool_calls,
            tools={"search": search_tool},
            interrupt_token=token,
        )

        # 关闭
        orchestrator.shutdown()
    """

    def __init__(
        self,
        settings: "Settings",
        approval_callback: Optional[ApprovalCallback] = None,
    ):
        """初始化工具编排器。

        Args:
            settings: 配置对象
            approval_callback: 审批回调（可选）
        """
        self._settings = settings
        self._approval_callback = approval_callback
        self._executor: Optional[ToolExecutor] = None
        self._approval_manager: Optional[ApprovalManager] = None

    def _ensure_executor(self) -> ToolExecutor:
        """确保执行器已创建。"""
        if self._executor is None:
            self._executor = ToolExecutor(
                max_workers=getattr(self._settings, 'max_workers', 4),
            )
        return self._executor

    def _ensure_approval_manager(self) -> ApprovalManager:
        """确保审批管理器已创建。"""
        if self._approval_manager is None:
            self._approval_manager = ApprovalManager()
            self._approval_manager.set_callback(self._approval_callback)
        return self._approval_manager

    def execute(
        self,
        tool_calls: List[ToolCall],
        tools: Dict[str, Tool],
        interrupt_token: Optional["InterruptToken"] = None,
    ) -> List[ToolResult]:
        """执行工具调用。

        Args:
            tool_calls: 工具调用列表
            tools: 工具字典
            interrupt_token: 中断令牌（可选）

        Returns:
            工具执行结果列表
        """
        if not tool_calls:
            return []

        executor = self._ensure_executor()
        approval_manager = self._ensure_approval_manager()

        # 设置中断令牌
        if interrupt_token:
            executor.set_interrupt_token(interrupt_token)

        results: List[ToolResult] = []

        for tc in tool_calls:
            # 查找工具
            tool = tools.get(tc.name)
            if tool is None:
                results.append(ToolResult(
                    tool_call_id=tc.id,
                    content=f"未找到工具: {tc.name}",
                    is_error=True,
                ))
                continue

            # 解析参数
            try:
                import json
                args = json.loads(tc.arguments) if tc.arguments else {}
            except json.JSONDecodeError as e:
                results.append(ToolResult(
                    tool_call_id=tc.id,
                    content=f"参数解析错误: {e}",
                    is_error=True,
                ))
                continue

            # 检查审批
            if approval_manager.needs_approval(tool, args):
                response = approval_manager.request_approval(tool, args)
                if response.decision.value == "deny":
                    results.append(ToolResult(
                        tool_call_id=tc.id,
                        content=f"工具调用被拒绝: {response.reason}",
                        is_error=True,
                    ))
                    continue

            # 执行工具
            result = executor.execute(tool, tc.id, **args)
            results.append(result)

        return results

    def execute_concurrent(
        self,
        tool_calls: List[ToolCall],
        tools: Dict[str, Tool],
        interrupt_token: Optional["InterruptToken"] = None,
    ) -> List[ToolResult]:
        """并发执行工具调用。

        Args:
            tool_calls: 工具调用列表
            tools: 工具字典
            interrupt_token: 中断令牌（可选）

        Returns:
            工具执行结果列表
        """
        if not tool_calls:
            return []

        executor = self._ensure_executor()

        # 设置中断令牌
        if interrupt_token:
            executor.set_interrupt_token(interrupt_token)

        # 构建调用列表
        calls = []
        for tc in tool_calls:
            tool = tools.get(tc.name)
            if tool is None:
                continue
            try:
                import json
                args = json.loads(tc.arguments) if tc.arguments else {}
            except json.JSONDecodeError:
                args = {}
            calls.append((tool, tc.id, args))

        # 并发执行
        return executor.execute_batch(calls)

    def shutdown(self) -> None:
        """关闭执行器。"""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    def __enter__(self) -> "ToolOrchestrator":
        """上下文管理器入口。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.shutdown()
