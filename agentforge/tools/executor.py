"""工具执行器。

提供并发执行、中断检查、ContextVars 传播等功能。
"""

from __future__ import annotations

import concurrent.futures
import contextvars
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from agentforge.tools.base import Tool
from agentforge.types import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ToolExecution:
    """工具执行记录。

    属性：
        tool_call_id: 工具调用 ID
        tool_name: 工具名称
        args: 工具参数
        result: 执行结果
        start_time: 开始时间
        end_time: 结束时间
        error: 错误信息（如果有）
    """

    tool_call_id: str
    tool_name: str
    args: Dict[str, Any]
    result: Optional[ToolResult] = None
    start_time: float = 0.0
    end_time: float = 0.0
    error: Optional[str] = None

    @property
    def duration(self) -> float:
        """执行耗时（秒）。"""
        if self.end_time > 0:
            return self.end_time - self.start_time
        return 0.0

    @property
    def success(self) -> bool:
        """是否执行成功。"""
        return self.result is not None and not self.result.is_error


class ToolExecutor:
    """工具执行器。

    功能：
    - 并发执行多个工具调用
    - 支持中断检查
    - ContextVars 传播到工作线程
    - 超时控制
    - 执行记录追踪

    使用示例：
        executor = ToolExecutor(max_workers=4)

        # 执行单个工具
        result = executor.execute(tool, tool_call_id="call-1", query="test")

        # 并发执行多个工具
        results = executor.execute_batch([
            (tool1, "call-1", {"query": "a"}),
            (tool2, "call-2", {"path": "/tmp"}),
        ])
    """

    def __init__(
        self,
        max_workers: int = 4,
        default_timeout: float = 300.0,
        interrupt_check_interval: float = 0.5,
    ):
        """初始化执行器。

        Args:
            max_workers: 最大并发工作线程数
            default_timeout: 默认超时时间（秒）
            interrupt_check_interval: 中断检查间隔（秒）
        """
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._interrupt_check_interval = interrupt_check_interval
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._executions: Dict[str, ToolExecution] = {}
        self._interrupt_token: Optional["InterruptToken"] = None

    def start(self) -> None:
        """启动执行器。"""
        with self._lock:
            if self._executor is None:
                self._executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="tool-worker",
                )

    def shutdown(self, wait: bool = True) -> None:
        """关闭执行器。

        Args:
            wait: 是否等待所有任务完成
        """
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=wait)
                self._executor = None

    def set_interrupt_token(self, token: Optional["InterruptToken"]) -> None:
        """设置中断令牌。

        Args:
            token: 中断令牌
        """
        self._interrupt_token = token

    def execute(
        self,
        tool: Tool,
        tool_call_id: str,
        **kwargs,
    ) -> ToolResult:
        """执行单个工具。

        Args:
            tool: 工具实例
            tool_call_id: 工具调用 ID
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        execution = ToolExecution(
            tool_call_id=tool_call_id,
            tool_name=tool.name,
            args=kwargs,
        )
        execution.start_time = time.time()

        try:
            # 检查中断
            if self._check_interrupt():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content="工具执行被中断",
                    is_error=True,
                )

            # 执行工具
            timeout = min(tool.timeout, self._default_timeout)
            result = tool.execute(tool_call_id, **kwargs)

            execution.result = result
            return result

        except Exception as e:
            execution.error = str(e)
            logger.error(f"工具执行错误 [{tool.name}]: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"工具执行错误: {e}",
                is_error=True,
            )

        finally:
            execution.end_time = time.time()
            with self._lock:
                self._executions[tool_call_id] = execution

    def execute_batch(
        self,
        calls: List[tuple[Tool, str, Dict[str, Any]]],
    ) -> List[ToolResult]:
        """并发执行多个工具。

        Args:
            calls: 工具调用列表，每项为 (tool, tool_call_id, args)

        Returns:
            工具执行结果列表（按输入顺序）
        """
        if not calls:
            return []

        # 确保执行器已启动
        if self._executor is None:
            self.start()

        # 捕获当前 ContextVars
        context = contextvars.copy_context()

        # 提交所有任务
        futures: List[concurrent.futures.Future] = []
        for tool, tool_call_id, args in calls:
            future = self._executor.submit(
                self._execute_with_context,
                context,
                tool,
                tool_call_id,
                args,
            )
            futures.append(future)

        # 等待所有任务完成
        results: List[ToolResult] = []
        for future in futures:
            try:
                result = future.result(timeout=self._default_timeout)
                results.append(result)
            except concurrent.futures.TimeoutError:
                results.append(ToolResult(
                    tool_call_id="",
                    content="工具执行超时",
                    is_error=True,
                ))
            except Exception as e:
                results.append(ToolResult(
                    tool_call_id="",
                    content=f"工具执行错误: {e}",
                    is_error=True,
                ))

        return results

    def _execute_with_context(
        self,
        context: contextvars.Context,
        tool: Tool,
        tool_call_id: str,
        args: Dict[str, Any],
    ) -> ToolResult:
        """在指定 ContextVars 上下文中执行工具。

        Args:
            context: ContextVars 上下文
            tool: 工具实例
            tool_call_id: 工具调用 ID
            args: 工具参数

        Returns:
            工具执行结果
        """
        # 在捕获的上下文中运行
        return context.run(self.execute, tool, tool_call_id, **args)

    def _check_interrupt(self) -> bool:
        """检查是否需要中断。

        Returns:
            True 如果需要中断
        """
        if self._interrupt_token is not None:
            return self._interrupt_token.check()
        return False

    def get_execution(self, tool_call_id: str) -> Optional[ToolExecution]:
        """获取执行记录。

        Args:
            tool_call_id: 工具调用 ID

        Returns:
            执行记录，如果不存在则返回 None
        """
        return self._executions.get(tool_call_id)

    def get_all_executions(self) -> Dict[str, ToolExecution]:
        """获取所有执行记录。"""
        return self._executions.copy()

    def clear_executions(self) -> None:
        """清空执行记录。"""
        with self._lock:
            self._executions.clear()

    def __enter__(self) -> "ToolExecutor":
        """上下文管理器入口。"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.shutdown(wait=True)


# 延迟导入，避免循环依赖
from agentforge.interrupt import InterruptToken
