"""工具执行器。

提供并发执行、中断检查、ContextVars 传播、超时控制、工具护栏等功能。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from hai_agent.tools.base import Tool
from hai_agent.tools.guardrails import ToolCallGuardrailController, ToolGuardrailDecision
from hai_agent.types import ToolResult

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
        timeout: 超时时间（秒）
    """

    tool_call_id: str
    tool_name: str
    args: Dict[str, Any]
    result: Optional[ToolResult] = None
    start_time: float = 0.0
    end_time: float = 0.0
    error: Optional[str] = None
    timeout: float = 0.0

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
    - 超时控制（实际生效）
    - 执行记录追踪
    - 工具护栏（循环检测、失败限制）

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
        enable_guardrails: bool = True,
    ):
        """初始化执行器。

        Args:
            max_workers: 最大并发工作线程数
            default_timeout: 默认超时时间（秒）
            interrupt_check_interval: 中断检查间隔（秒）
            enable_guardrails: 是否启用工具护栏
        """
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._interrupt_check_interval = interrupt_check_interval
        self._enable_guardrails = enable_guardrails
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self._executions: Dict[str, ToolExecution] = {}
        self._interrupt_token: Optional["InterruptToken"] = None
        self._guardrail_controller: Optional[ToolCallGuardrailController] = None

        if enable_guardrails:
            self._guardrail_controller = ToolCallGuardrailController()

    def start(self) -> None:
        """启动执行器。"""
        with self._sync_lock:
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
        with self._sync_lock:
            if self._executor is not None:
                self._executor.shutdown(wait=wait)
                self._executor = None

    def set_interrupt_token(self, token: Optional["InterruptToken"]) -> None:
        """设置中断令牌。

        Args:
            token: 中断令牌
        """
        self._interrupt_token = token

    def reset_guardrails(self) -> None:
        """重置护栏控制器。"""
        if self._guardrail_controller:
            self._guardrail_controller.reset_for_turn()

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

            # 护栏检查（执行前）
            if self._guardrail_controller:
                decision = self._guardrail_controller.before_call(tool.name, kwargs)
                if not decision.allows_execution:
                    logger.warning(f"工具护栏阻止执行: {decision.message}")
                    return ToolResult(
                        tool_call_id=tool_call_id,
                        content=decision.message,
                        is_error=True,
                    )

            # 计算超时
            timeout = min(tool.timeout, self._default_timeout)
            execution.timeout = timeout

            # 执行工具（带超时）
            result = self._execute_with_timeout(tool, tool_call_id, timeout, **kwargs)

            # 护栏记录（执行后）
            if self._guardrail_controller:
                self._guardrail_controller.after_call(
                    tool.name,
                    kwargs,
                    result.content if result else None,
                    failed=result.is_error if result else True,
                )

            execution.result = result
            return result

        except (RuntimeError, ValueError, TypeError, TimeoutError) as e:
            execution.error = str(e)
            logger.error(f"工具执行错误 [{tool.name}]: {e}")

            # 护栏记录失败
            if self._guardrail_controller:
                self._guardrail_controller.after_call(
                    tool.name,
                    kwargs,
                    str(e),
                    failed=True,
                )

            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"工具执行错误: {e}",
                is_error=True,
            )

        finally:
            execution.end_time = time.time()
            with self._sync_lock:
                self._executions[tool_call_id] = execution

    def _execute_with_timeout(
        self,
        tool: Tool,
        tool_call_id: str,
        timeout: float,
        **kwargs,
    ) -> ToolResult:
        """带超时执行工具。

        Args:
            tool: 工具实例
            tool_call_id: 工具调用 ID
            timeout: 超时时间（秒）
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        # 如果工具支持超时，直接传递
        if hasattr(tool, "timeout"):
            try:
                return tool.execute(tool_call_id, timeout=timeout, **kwargs)
            except TypeError:
                # 工具不支持 timeout 参数
                pass

        # 使用线程执行并等待
        result_container = {"result": None, "error": None}
        event = threading.Event()

        def _run():
            try:
                result_container["result"] = tool.execute(tool_call_id, **kwargs)
            except (RuntimeError, ValueError, TypeError) as e:
                result_container["error"] = e
            finally:
                event.set()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        # 等待完成或超时
        if event.wait(timeout=timeout):
            if result_container["error"]:
                raise result_container["error"]
            return result_container["result"]
        else:
            # 超时
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"工具执行超时（{timeout}秒）",
                is_error=True,
            )

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
            except (RuntimeError, ValueError, TypeError) as e:
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
        with self._sync_lock:
            self._executions.clear()

    # === 异步方法 ===

    async def execute_async(
        self,
        tool: Tool,
        tool_call_id: str,
        **kwargs,
    ) -> ToolResult:
        """异步执行单个工具。

        Args:
            tool: 工具实例
            tool_call_id: 工具调用 ID
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute(tool, tool_call_id, **kwargs),
        )

    async def execute_batch_async(
        self,
        calls: List[tuple[Tool, str, Dict[str, Any]]],
    ) -> List[ToolResult]:
        """异步并发执行多个工具。

        使用 asyncio.gather 并行执行，而不是 ThreadPoolExecutor。

        Args:
            calls: 工具调用列表，每项为 (tool, tool_call_id, args)

        Returns:
            工具执行结果列表（按输入顺序）
        """
        if not calls:
            return []

        # 创建异步任务列表
        tasks = [
            self.execute_async(tool, tool_call_id, **args)
            for tool, tool_call_id, args in calls
        ]

        # 并行执行
        return await asyncio.gather(*tasks, return_exceptions=False)

    def __enter__(self) -> "ToolExecutor":
        """上下文管理器入口。"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.shutdown(wait=True)


# 延迟导入，避免循环依赖
from hai_agent.interrupt import InterruptToken
