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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Union

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

# 新增
from agentforge.profiles.profile import AgentProfile

if TYPE_CHECKING:
    from agentforge.agent import Agent
    from agentforge.config import Settings
    from agentforge.providers import Provider
    from agentforge.profiles import ProfileRegistry, ProviderRegistry

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
        profile_registry: Optional["ProfileRegistry"] = None,
        provider_registry: Optional["ProviderRegistry"] = None,
    ):
        """初始化委托管理器。

        Args:
            config: 委托配置
            parent_agent: 父 Agent
            event_dispatcher: 事件分发器
            profile_registry: Profile 注册表
            provider_registry: Provider 注册表
        """
        self._config = config or DelegationConfig()
        self._parent_agent = parent_agent
        self._event_dispatcher = event_dispatcher
        self._profile_registry = profile_registry
        self._provider_registry = provider_registry

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

            # 创建子 Agent
            child_agent = self._create_child_agent(task, system_prompt)

            if child_agent is None:
                # 无法创建子 Agent，返回模拟结果
                duration = time.monotonic() - start_time
                return TaskResult(
                    task_index=task_index,
                    status=DelegationStatus.COMPLETED,
                    summary=f"任务完成（模拟）: {task.goal[:100]}",
                    exit_reason=ExitReason.COMPLETED,
                    duration_seconds=duration,
                )

            # 发射工具开始事件
            self._emit_event(EventType.TOOL_START, {
                "subagent_id": subagent_id,
                "goal": task.goal,
            })

            # 执行子 Agent
            child_token = child_agent.get_interrupt_token()

            # 运行子 Agent
            response = child_agent.run(
                message=task.goal,
                max_iterations=self._config.isolation.max_iterations,
                interrupt_token=child_token,
            )

            # 检查是否被中断
            if interrupt_token and interrupt_token.check():
                return TaskResult(
                    task_index=task_index,
                    status=DelegationStatus.INTERRUPTED,
                    exit_reason=ExitReason.INTERRUPTED,
                )

            # 提取结果
            duration = time.monotonic() - start_time
            summary = response.content if response.content else "任务完成（无输出）"

            # 计算 Token 使用
            tokens = {"input": 0, "output": 0}
            if response.usage:
                tokens["input"] = response.usage.prompt_tokens
                tokens["output"] = response.usage.completion_tokens

            result = TaskResult(
                task_index=task_index,
                status=DelegationStatus.COMPLETED,
                summary=summary,
                exit_reason=ExitReason.COMPLETED,
                duration_seconds=duration,
                tokens=tokens,
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

    def _create_child_agent(
        self,
        task: TaskSpec,
        system_prompt: str,
    ) -> Optional["Agent"]:
        """创建子 Agent。

        Args:
            task: 任务规格
            system_prompt: 系统提示

        Returns:
            子 Agent 实例，如果无法创建则返回 None
        """
        if self._parent_agent is None:
            return None

        try:
            # 获取父 Agent 的 Provider
            provider = getattr(self._parent_agent, "_provider", None)
            if provider is None:
                return None

            # 获取父 Agent 的设置
            settings = getattr(self._parent_agent, "_settings", None)

            # 构建子 Agent 的工具集
            child_tools = self._build_child_tools(task)

            # 导入 Agent 类（延迟导入避免循环依赖）
            from agentforge.agent import Agent

            # 创建子 Agent
            child_agent = Agent(
                provider=provider,
                settings=settings,
                tools=child_tools,
            )

            # 设置委托深度
            parent_depth = getattr(self._parent_agent, "_delegate_depth", 0)
            child_agent._delegate_depth = parent_depth + 1

            # 设置系统提示（如果 Provider 支持）
            if hasattr(child_agent, "_message_manager"):
                child_agent._message_manager.set_system_prompt(system_prompt)

            return child_agent

        except Exception as e:
            logger.error(f"创建子 Agent 失败: {e}")
            return None

    def _build_child_tools(self, task: TaskSpec) -> List[Any]:
        """构建子 Agent 的工具集。

        Args:
            task: 任务规格

        Returns:
            工具列表
        """
        # 获取父 Agent 的工具
        parent_tools = {}
        if self._parent_agent:
            parent_tools = getattr(self._parent_agent, "_tools", {})

        # 被阻止的工具
        blocked_tools = self._config.isolation.blocked_tools

        # 根据任务指定的工具集过滤
        allowed_tool_names: Optional[Set[str]] = None
        if task.toolsets:
            # 解析工具集，获取允许的工具名称
            from agentforge.tools.toolsets import resolve_toolset

            allowed_tool_names = set()
            for toolset_name in task.toolsets:
                tools_in_toolset = resolve_toolset(toolset_name)
                allowed_tool_names.update(tools_in_toolset)

            logger.debug(
                f"任务工具集 {task.toolsets} 解析为工具: {allowed_tool_names}"
            )

        # 过滤被阻止的工具
        child_tools = []
        for name, tool in parent_tools.items():
            # 检查是否在阻止列表
            if name in blocked_tools:
                continue

            # 检查是否在允许的工具集范围内
            if allowed_tool_names is not None:
                # 使用工具名称或别名检查
                tool_names = {name}
                if hasattr(tool, "name"):
                    tool_names.add(tool.name)
                if not tool_names.intersection(allowed_tool_names):
                    continue

            child_tools.append(tool)

        return child_tools

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

    def _resolve_profile(
        self,
        profile_name: str,
        task: TaskSpec,
    ) -> Optional[AgentProfile]:
        """解析并验证 Profile。

        Args:
            profile_name: Profile 名称
            task: 任务规格

        Returns:
            解析后的 Profile，如果无效则返回 None
        """
        if self._profile_registry is None:
            logger.debug("ProfileRegistry 未配置")
            return None

        profile = self._profile_registry.get(profile_name)
        if profile is None:
            logger.warning(f"Profile '{profile_name}' 不存在")
            self._emit_event(EventType.PROFILE_INVALID, {
                "profile": profile_name,
                "errors": ["Profile 不存在"],
            })
            return None

        # 验证 Profile
        errors, warnings = profile.validate(self._provider_registry)
        if errors:
            logger.error(f"Profile '{profile_name}' 验证失败: {errors}")
            self._emit_event(EventType.PROFILE_INVALID, {
                "profile": profile_name,
                "errors": errors,
                "warnings": warnings,
            })
            return None

        if warnings:
            logger.warning(f"Profile '{profile_name}' 警告: {warnings}")

        # 发射加载事件
        self._emit_event(EventType.PROFILE_LOADED, {
            "profile": profile_name,
            "provider": profile.provider,
            "model": profile.model,
        })

        return profile

    def _resolve_child_config(
        self,
        task: TaskSpec,
        profile: Optional[AgentProfile],
        system_prompt: str,
    ) -> tuple:
        """解析子 Agent 的最终配置。

        优先级：task 覆盖 > Profile 配置 > 父 Agent 回退

        Args:
            task: 任务规格
            profile: Profile 对象（可选）
            system_prompt: 基础系统提示

        Returns:
            (provider_name, model, settings_dict)
        """
        # 默认从父 Agent 获取
        parent_provider = getattr(
            getattr(self._parent_agent, "_provider", None),
            "name",
            None
        )
        parent_model = getattr(self._parent_agent, "_settings", None)
        parent_model = getattr(parent_model, "model", None) if parent_model else None
        parent_temp = getattr(self._parent_agent, "_settings", None)
        parent_temp = getattr(parent_temp, "temperature", 1.0) if parent_temp else 1.0
        parent_tokens = getattr(self._parent_agent, "_settings", None)
        parent_tokens = getattr(parent_tokens, "max_tokens", 4096) if parent_tokens else 4096

        # Provider: task > profile > 父 Agent
        provider_name = None
        if profile and profile.provider:
            if self._provider_registry and self._provider_registry.is_available(profile.provider):
                provider_name = profile.provider
        if provider_name is None:
            provider_name = parent_provider

        # Model: task > profile > 父 Agent
        model = task.model
        if model is None and profile:
            model = profile.model
        if model is None:
            model = parent_model

        # Temperature: task > profile > 父 Agent
        temperature = task.temperature
        if temperature is None and profile:
            temperature = profile.temperature
        if temperature is None:
            temperature = parent_temp

        # Max tokens: task > profile > 父 Agent
        max_tokens = task.max_tokens
        if max_tokens is None and profile:
            max_tokens = profile.max_tokens
        if max_tokens is None:
            max_tokens = parent_tokens

        # System prompt: base + profile + task append
        final_prompt = system_prompt
        if profile and profile.system_prompt:
            final_prompt = f"{system_prompt}\n\n{profile.system_prompt}"
        if task.system_prompt:
            final_prompt = f"{final_prompt}\n\n{task.system_prompt}"

        settings_dict = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system_prompt": final_prompt,
        }

        return provider_name, model, settings_dict

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

    # === 异步方法 ===

    async def delegate_async(
        self,
        goal: str,
        context: Optional[str] = None,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> DelegationResult:
        """异步执行单任务委托。

        Args:
            goal: 任务目标
            context: 任务上下文（可选）
            interrupt_token: 中断令牌（可选）

        Returns:
            委托结果
        """
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.delegate(goal, context, interrupt_token),
        )

    async def delegate_batch_async(
        self,
        tasks: List[TaskSpec],
        strategy: DelegationStrategy = DelegationStrategy.SEQUENTIAL,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> DelegationResult:
        """异步执行批量委托。

        根据策略选择执行方式：
        - SEQUENTIAL: 顺序执行
        - PARALLEL: 使用 asyncio.gather 并行执行

        Args:
            tasks: 任务规格列表
            strategy: 执行策略
            interrupt_token: 中断令牌（可选）

        Returns:
            委托结果
        """
        import asyncio

        if strategy == DelegationStrategy.PARALLEL:
            return await self._delegate_parallel_async(tasks, interrupt_token)
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: self.delegate_batch(tasks, strategy, interrupt_token),
            )

    async def _delegate_parallel_async(
        self,
        tasks: List[TaskSpec],
        interrupt_token: Optional[InterruptToken] = None,
    ) -> DelegationResult:
        """异步并行执行多个任务。

        使用 asyncio.gather 并行执行所有任务。

        Args:
            tasks: 任务规格列表
            interrupt_token: 中断令牌（可选）

        Returns:
            委托结果
        """
        import asyncio

        start_time = time.monotonic()

        # 发射委托开始事件
        self._emit_event(EventType.DELEGATION_START, {
            "task_count": len(tasks),
            "strategy": "parallel_async",
        })

        # 创建并行任务
        async def run_single_task(index: int, task: TaskSpec) -> TaskResult:
            return await asyncio.to_thread(
                self._execute_single_task,
                index,
                task,
                interrupt_token,
            )

        # 并行执行
        coros = [run_single_task(i, task) for i, task in enumerate(tasks)]
        task_results = await asyncio.gather(*coros, return_exceptions=True)

        # 处理结果
        results: List[TaskResult] = []
        for i, result in enumerate(task_results):
            if isinstance(result, Exception):
                results.append(TaskResult(
                    task_index=i,
                    status=DelegationStatus.FAILED,
                    error=str(result),
                    exit_reason=ExitReason.ERROR,
                ))
            else:
                results.append(result)

        # 构建最终结果
        duration = time.monotonic() - start_time
        final_result = DelegationResult(
            status=DelegationStatus.COMPLETED,
            task_results=results,
            strategy_used=DelegationStrategy.PARALLEL,
            duration_seconds=duration,
        )

        # 发射委托结束事件
        self._emit_event(EventType.DELEGATION_END, {
            "status": final_result.status.value,
            "duration": duration,
        })

        return final_result

    def clear(self) -> None:
        """清空所有状态。"""
        with self._active_children_lock:
            self._active_children.clear()
        self.set_spawn_paused(False)
