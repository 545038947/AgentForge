"""委托管理器。

负责子 Agent 的创建、执行和结果聚合。
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

from agentforge.delegation.config import DelegationConfig, IsolationConfig, TaskSpec
from agentforge.delegation.result import (
    DelegationResult,
    DelegationStatus,
    DelegationStrategy,
    ExitReason,
    TaskResult,
)
from agentforge.events import EventType
from agentforge.interrupt import InterruptToken
from agentforge.types import NormalizedResponse

if TYPE_CHECKING:
    from agentforge.agent import Agent
    from agentforge.config import Settings
    from agentforge.providers import Provider

logger = logging.getLogger(__name__)


class DelegationManager:
    """委托管理器。

    负责：
    - 管理委托配置
    - 创建和执行子 Agent
    - 聚合结果
    - 处理中断和超时

    使用示例：
        manager = DelegationManager(config, parent_agent)

        # 单任务委托
        result = manager.delegate(
            goal="搜索相关文档",
            context="项目背景信息",
        )

        # 批量委托
        result = manager.delegate_batch([
            TaskSpec(goal="任务1"),
            TaskSpec(goal="任务2"),
        ])
    """

    def __init__(
        self,
        config: Optional[DelegationConfig] = None,
        parent_agent: Optional["Agent"] = None,
        event_dispatcher: Optional[Any] = None,
    ):
        """初始化委托管理器。

        Args:
            config: 委托配置
            parent_agent: 父 Agent
            event_dispatcher: 事件分发器
        """
        self._config = config or DelegationConfig()
        self._parent_agent = parent_agent
        self._event_dispatcher = event_dispatcher

        # 活跃子 Agent 注册表
        self._active_children: Dict[str, Any] = {}
        self._active_children_lock = threading.Lock()

        # 暂停标志
        self._spawn_paused = False
        self._spawn_paused_lock = threading.Lock()

    def set_parent_agent(self, agent: "Agent") -> None:
        """设置父 Agent。

        Args:
            agent: 父 Agent 实例
        """
        self._parent_agent = agent

    def set_event_dispatcher(self, dispatcher: Any) -> None:
        """设置事件分发器。

        Args:
            dispatcher: 事件分发器
        """
        self._event_dispatcher = dispatcher

    def delegate(
        self,
        goal: str,
        context: Optional[str] = None,
        toolsets: Optional[List[str]] = None,
        role: str = "leaf",
        model: Optional[str] = None,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> DelegationResult:
        """委托单个任务。

        Args:
            goal: 任务目标
            context: 任务上下文
            toolsets: 工具集列表
            role: 角色（leaf 或 orchestrator）
            model: 模型名称
            interrupt_token: 中断令牌

        Returns:
            委托结果
        """
        task = TaskSpec(
            goal=goal,
            context=context,
            toolsets=toolsets,
            role=role,
            model=model,
        )
        return self.delegate_batch([task], interrupt_token=interrupt_token)

    def delegate_batch(
        self,
        tasks: List[TaskSpec],
        strategy: DelegationStrategy = DelegationStrategy.PARALLEL,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> DelegationResult:
        """批量委托任务。

        Args:
            tasks: 任务列表
            strategy: 执行策略
            interrupt_token: 中断令牌

        Returns:
            委托结果
        """
        if not tasks:
            return DelegationResult(status=DelegationStatus.COMPLETED)

        # 检查暂停状态
        if self.is_spawn_paused():
            return DelegationResult(
                status=DelegationStatus.FAILED,
                results=[TaskResult(
                    task_index=0,
                    status=DelegationStatus.FAILED,
                    error="委托已暂停",
                )],
            )

        # 检查深度限制
        depth = self._get_current_depth()
        if depth >= self._config.max_depth:
            return DelegationResult(
                status=DelegationStatus.FAILED,
                results=[TaskResult(
                    task_index=0,
                    status=DelegationStatus.FAILED,
                    error=f"委托深度限制（depth={depth}, max={self._config.max_depth}）",
                )],
            )

        # 发射委托开始事件
        self._emit_event(EventType.DELEGATION_START, {"task_count": len(tasks)})

        start_time = time.monotonic()
        results: List[TaskResult] = []

        try:
            if strategy == DelegationStrategy.PARALLEL and len(tasks) > 1:
                results = self._execute_parallel(tasks, interrupt_token)
            else:
                results = self._execute_sequential(tasks, interrupt_token)

            # 计算总时长和 Token
            total_duration = time.monotonic() - start_time
            total_tokens = {"input": 0, "output": 0}
            for r in results:
                total_tokens["input"] += r.tokens.get("input", 0)
                total_tokens["output"] += r.tokens.get("output", 0)

            # 确定整体状态
            all_success = all(r.is_success() for r in results)
            status = DelegationStatus.COMPLETED if all_success else DelegationStatus.FAILED

            # 发射委托结束事件
            self._emit_event(EventType.DELEGATION_END, {
                "status": status.value,
                "task_count": len(tasks),
            })

            return DelegationResult(
                status=status,
                results=results,
                strategy=strategy,
                total_duration=total_duration,
                total_tokens=total_tokens,
            )

        except Exception as e:
            logger.error(f"委托执行错误: {e}")
            return DelegationResult(
                status=DelegationStatus.FAILED,
                results=[TaskResult(
                    task_index=0,
                    status=DelegationStatus.FAILED,
                    error=str(e),
                )],
            )

    def _execute_sequential(
        self,
        tasks: List[TaskSpec],
        interrupt_token: Optional[InterruptToken] = None,
    ) -> List[TaskResult]:
        """顺序执行任务。

        Args:
            tasks: 任务列表
            interrupt_token: 中断令牌

        Returns:
            任务结果列表
        """
        results = []
        for i, task in enumerate(tasks):
            # 检查中断
            if interrupt_token and interrupt_token.check():
                results.append(TaskResult(
                    task_index=i,
                    status=DelegationStatus.INTERRUPTED,
                    exit_reason=ExitReason.INTERRUPTED,
                ))
                break

            result = self._execute_single(i, task, interrupt_token)
            results.append(result)

        return results

    def _execute_parallel(
        self,
        tasks: List[TaskSpec],
        interrupt_token: Optional[InterruptToken] = None,
    ) -> List[TaskResult]:
        """并行执行任务。

        Args:
            tasks: 任务列表
            interrupt_token: 中断令牌

        Returns:
            任务结果列表
        """
        max_workers = min(len(tasks), self._config.max_concurrent)
        results = [None] * len(tasks)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for i, task in enumerate(tasks):
                future = executor.submit(
                    self._execute_single,
                    i, task, interrupt_token,
                )
                futures[future] = i

            for future in concurrent.futures.as_completed(futures):
                i = futures[future]
                try:
                    results[i] = future.result(timeout=self._config.isolation.timeout)
                except concurrent.futures.TimeoutError:
                    results[i] = TaskResult(
                        task_index=i,
                        status=DelegationStatus.TIMEOUT,
                        exit_reason=ExitReason.TIMEOUT,
                    )
                except Exception as e:
                    results[i] = TaskResult(
                        task_index=i,
                        status=DelegationStatus.FAILED,
                        error=str(e),
                        exit_reason=ExitReason.ERROR,
                    )

        return results

    def _execute_single(
        self,
        task_index: int,
        task: TaskSpec,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> TaskResult:
        """执行单个任务。

        Args:
            task_index: 任务索引
            task: 任务规格
            interrupt_token: 中断令牌

        Returns:
            任务结果
        """
        start_time = time.monotonic()
        subagent_id = f"sa-{task_index}-{uuid.uuid4().hex[:8]}"

        # 注册子 Agent
        self._register_child(subagent_id, {"goal": task.goal, "status": "running"})

        try:
            # 检查中断
            if interrupt_token and interrupt_token.check():
                return TaskResult(
                    task_index=task_index,
                    status=DelegationStatus.INTERRUPTED,
                    exit_reason=ExitReason.INTERRUPTED,
                )

            # 构建子 Agent 系统提示
            system_prompt = self._build_child_prompt(task)

            # 模拟执行（实际实现需要创建子 Agent）
            # 这里提供一个简化的实现框架
            duration = time.monotonic() - start_time

            # 发射工具开始事件
            self._emit_event(EventType.TOOL_START, {
                "subagent_id": subagent_id,
                "goal": task.goal,
            })

            # 模拟结果
            result = TaskResult(
                task_index=task_index,
                status=DelegationStatus.COMPLETED,
                summary=f"任务完成: {task.goal[:100]}",
                exit_reason=ExitReason.COMPLETED,
                duration_seconds=duration,
            )

            # 发射工具结束事件
            self._emit_event(EventType.TOOL_END, {
                "subagent_id": subagent_id,
                "status": result.status.value,
            })

            return result

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(f"子 Agent 执行错误: {e}")
            return TaskResult(
                task_index=task_index,
                status=DelegationStatus.FAILED,
                error=str(e),
                exit_reason=ExitReason.ERROR,
                duration_seconds=duration,
            )

        finally:
            self._unregister_child(subagent_id)

    def _build_child_prompt(self, task: TaskSpec) -> str:
        """构建子 Agent 系统提示。

        Args:
            task: 任务规格

        Returns:
            系统提示文本
        """
        parts = [
            "你是一个专注于特定任务的子 Agent。",
            "",
            f"任务目标：\n{task.goal}",
        ]

        if task.context:
            parts.append(f"\n上下文：\n{task.context}")

        parts.append("""
完成此任务后，请提供清晰的摘要：
- 你做了什么
- 发现或完成了什么
- 创建或修改了哪些文件
- 遇到的问题

请简洁但完整——你的响应将作为摘要返回给父 Agent。
""")

        if task.role == "orchestrator":
            parts.append("""
## 子 Agent 委托（编排者角色）
你可以使用 delegate_task 工具来并行处理独立的工作。
""")

        return "\n".join(parts)

    def _get_current_depth(self) -> int:
        """获取当前委托深度。

        Returns:
            当前深度
        """
        if self._parent_agent is None:
            return 0
        return getattr(self._parent_agent, "_delegate_depth", 0) + 1

    def _register_child(self, child_id: str, record: Dict[str, Any]) -> None:
        """注册子 Agent。

        Args:
            child_id: 子 Agent ID
            record: 注册记录
        """
        with self._active_children_lock:
            self._active_children[child_id] = record

    def _unregister_child(self, child_id: str) -> None:
        """取消注册子 Agent。

        Args:
            child_id: 子 Agent ID
        """
        with self._active_children_lock:
            self._active_children.pop(child_id, None)

    def interrupt_child(self, child_id: str) -> bool:
        """中断子 Agent。

        Args:
            child_id: 子 Agent ID

        Returns:
            是否成功中断
        """
        with self._active_children_lock:
            record = self._active_children.get(child_id)
            if record is None:
                return False

            agent = record.get("agent")
            if agent is None:
                return False

            try:
                if hasattr(agent, "interrupt"):
                    agent.interrupt(f"通过委托管理器中断 ({child_id})")
                return True
            except Exception as e:
                logger.debug(f"中断子 Agent 失败: {e}")
                return False

    def list_active_children(self) -> List[Dict[str, Any]]:
        """列出活跃的子 Agent。

        Returns:
            子 Agent 信息列表
        """
        with self._active_children_lock:
            return [
                {"id": cid, **{k: v for k, v in rec.items() if k != "agent"}}
                for cid, rec in self._active_children.items()
            ]

    def set_spawn_paused(self, paused: bool) -> bool:
        """设置暂停状态。

        Args:
            paused: 是否暂停

        Returns:
            新的暂停状态
        """
        with self._spawn_paused_lock:
            self._spawn_paused = paused
            return self._spawn_paused

    def is_spawn_paused(self) -> bool:
        """检查是否暂停。

        Returns:
            是否暂停
        """
        with self._spawn_paused_lock:
            return self._spawn_paused

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """发射事件。

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self._event_dispatcher:
            try:
                self._event_dispatcher.dispatch(event_type, data)
            except Exception as e:
                logger.debug(f"发射事件失败: {e}")

    def clear(self) -> None:
        """清空所有状态。"""
        with self._active_children_lock:
            self._active_children.clear()
        self.set_spawn_paused(False)
