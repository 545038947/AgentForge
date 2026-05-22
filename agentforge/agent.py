"""Agent 门面类。

整合所有组件，提供统一的 Agent 接口。
使用 ExecutionEngine 处理重试循环和错误恢复。
"""

from __future__ import annotations

import logging
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Union,
)

from agentforge.config import Settings
from agentforge.events import EventDispatcher, EventType
from agentforge.interrupt import InterruptHandler, InterruptToken
from agentforge.managers import MessageManager, ToolOrchestrator
from agentforge.context import ContextCompressor
from agentforge.tools import Tool, FunctionTool, ApprovalCallback
from agentforge.types import Message, NormalizedResponse, ToolResult
from agentforge.core import (
    IterationBudget,
    FallbackChain,
    ExecutionEngine,
    ExecutionConfig,
    ExecutionResult,
)
from agentforge.tools.guardrails import ToolCallGuardrailController

if TYPE_CHECKING:
    from agentforge.providers import Provider
    from agentforge.memory import MemoryManager, MemoryProvider
    from agentforge.skills import Skill, SkillRegistry

logger = logging.getLogger(__name__)


class Agent:
    """Agent 门面类。

    整合所有组件，提供统一的 Agent 接口。

    组件：
    - MessageManager: 消息历史管理
    - ToolOrchestrator: 工具执行编排
    - EventDispatcher: 事件分发
    - InterruptHandler: 中断处理
    - ExecutionEngine: 执行引擎（重试、回退、恢复）
    - FallbackChain: Provider 回退链
    - ToolCallGuardrailController: 工具护栏
    - MemoryManager: 记忆管理（可选）
    - SkillRegistry: 技能注册表（可选）

    生命周期：
    1. prefetch() - 预取记忆数据
    2. run() / stream() - 执行对话
    3. sync() - 同步记忆数据

    使用示例：
        agent = Agent(provider, settings)

        # 添加记忆提供者
        agent.add_memory("session", InMemoryProvider())

        # 添加技能
        agent.add_skill(search_skill)

        # 运行对话
        agent.prefetch()
        response = agent.run("你好")
        agent.sync()

        # 流式响应
        for chunk in agent.stream("继续"):
            print(chunk.content)
    """

    def __init__(
        self,
        provider: "Provider",
        settings: Optional[Settings] = None,
        tools: Optional[List[Union[Tool, Callable]]] = None,
        approval_callback: Optional[ApprovalCallback] = None,
        fallback_chain: Optional[FallbackChain] = None,
        memory_manager: Optional["MemoryManager"] = None,
        skill_registry: Optional["SkillRegistry"] = None,
    ):
        """初始化 Agent。

        Args:
            provider: Provider 实例
            settings: 配置对象（可选）
            tools: 工具列表（可选）
            approval_callback: 审批回调（可选）
            fallback_chain: 回退链（可选）
            memory_manager: 记忆管理器（可选）
            skill_registry: 技能注册表（可选）
        """
        self._provider = provider
        self._settings = settings or Settings()

        # 初始化组件
        self._compressor = ContextCompressor(self._settings.compression)
        self._message_manager = MessageManager(
            self._settings,
            compressor=self._compressor,
        )
        self._tool_orchestrator = ToolOrchestrator(
            self._settings,
            approval_callback=approval_callback,
        )
        self._event_dispatcher = EventDispatcher()
        self._interrupt_handler = InterruptHandler()

        # 回退链
        self._fallback_chain = fallback_chain

        # 工具护栏
        self._guardrails = ToolCallGuardrailController()

        # 工具注册表
        self._tools: Dict[str, Tool] = {}

        # 记忆管理器
        self._memory_manager = memory_manager
        if memory_manager is None:
            # 延迟导入避免循环依赖
            from agentforge.memory import MemoryManager
            self._memory_manager = MemoryManager(
                event_dispatcher=self._event_dispatcher,
            )

        # 技能注册表
        self._skill_registry = skill_registry
        if skill_registry is None:
            from agentforge.skills import SkillRegistry
            self._skill_registry = SkillRegistry()

        # 注册工具
        if tools:
            for t in tools:
                self.add_tool(t)

        # 执行引擎
        self._execution_engine = ExecutionEngine(
            provider=self._provider,
            config=ExecutionConfig(
                max_retries=self._settings.max_retries,
                enable_fallback=fallback_chain is not None,
                enable_compression=True,
                enable_guardrails=True,
            ),
            fallback_chain=self._fallback_chain,
            guardrails=self._guardrails,
            context_compressor=self._compressor,
            event_dispatcher=self._event_dispatcher,
        )

        # 迭代预算
        self._iteration_budget = IterationBudget(
            max_total=self._settings.max_iterations,
        )

        # 委托深度
        self._delegate_depth = 0

        # Agent 状态追踪（用于诊断和监控）
        self._last_activity_ts: float = time.time()
        self._last_activity_desc: str = "初始化"
        self._rate_limit_state: Optional[Dict[str, Any]] = None
        self._api_call_count: int = 0

    def add_tool(self, tool: Union[Tool, Callable]) -> Tool:
        """添加工具。

        Args:
            tool: 工具实例或函数

        Returns:
            注册的 Tool 实例
        """
        if callable(tool) and not isinstance(tool, Tool):
            tool = FunctionTool(tool)

        self._tools[tool.name] = tool
        return tool

    def tool(self, func: Callable) -> Tool:
        """工具装饰器。

        Args:
            func: 函数

        Returns:
            注册的 Tool 实例
        """
        return self.add_tool(func)

    # === 记忆管理 ===

    def add_memory(
        self,
        name: str,
        provider: "MemoryProvider",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加记忆提供者。

        Args:
            name: 提供者名称
            provider: MemoryProvider 实例
            config: 配置（可选）
        """
        if self._memory_manager is None:
            from agentforge.memory import MemoryManager
            self._memory_manager = MemoryManager(
                event_dispatcher=self._event_dispatcher,
            )

        self._memory_manager.register(name, provider, config)

    def get_memory(self, name: str) -> Optional["MemoryProvider"]:
        """获取记忆提供者。

        Args:
            name: 提供者名称

        Returns:
            MemoryProvider 实例
        """
        if self._memory_manager is None:
            return None
        return self._memory_manager.get_provider(name)

    def prefetch(
        self,
        keys: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """预取记忆数据。

        在运行对话前预加载记忆数据到缓存。

        Args:
            keys: 每个 provider 要预取的键列表

        Returns:
            预取结果
        """
        if self._memory_manager is None:
            return {}

        result = self._memory_manager.prefetch_all(keys)

        # 将记忆信息添加到系统提示
        memory_prompt = self._memory_manager.build_system_prompt()
        if memory_prompt:
            self._message_manager.add_memory_context(memory_prompt)

        return result

    async def prefetch_async(
        self,
        keys: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """异步预取记忆数据。"""
        if self._memory_manager is None:
            return {}

        result = await self._memory_manager.prefetch_all_async(keys)

        memory_prompt = self._memory_manager.build_system_prompt()
        if memory_prompt:
            self._message_manager.add_memory_context(memory_prompt)

        return result

    def sync(self) -> Dict[str, int]:
        """同步记忆数据。

        将缓存中的数据写回 provider。

        Returns:
            每个 provider 同步的条目数
        """
        if self._memory_manager is None:
            return {}

        return self._memory_manager.sync_all()

    async def sync_async(self) -> Dict[str, int]:
        """异步同步记忆数据。"""
        if self._memory_manager is None:
            return {}

        return await self._memory_manager.sync_all_async()

    def save_memory(
        self,
        provider_name: str,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """保存数据到记忆。

        Args:
            provider_name: provider 名称
            key: 键名
            value: 值
            metadata: 元数据

        Returns:
            是否成功保存
        """
        if self._memory_manager is None:
            logger.warning("记忆管理器未初始化")
            return False

        return self._memory_manager.save_to(provider_name, key, value, metadata)

    def load_memory(
        self,
        provider_name: str,
        key: str,
        use_cache: bool = True,
    ) -> Optional[Any]:
        """从记忆加载数据。

        Args:
            provider_name: provider 名称
            key: 键名
            use_cache: 是否使用缓存

        Returns:
            加载的值
        """
        if self._memory_manager is None:
            return None

        return self._memory_manager.load_from(provider_name, key, use_cache)

    # === 技能管理 ===

    def add_skill(self, skill: "Skill") -> None:
        """添加技能。

        Args:
            skill: Skill 实例
        """
        if self._skill_registry is None:
            from agentforge.skills import SkillRegistry
            self._skill_registry = SkillRegistry()

        self._skill_registry.register(skill)

        # 注册技能的工具
        skill_tools = skill.get_tools()
        for tool in skill_tools:
            self.add_tool(tool)

        # 添加技能的提示模板
        prompt_template = skill.get_prompt_template()
        if prompt_template:
            self._message_manager.add_skill_prompt(skill.name, prompt_template)

    def get_skill(self, name: str) -> Optional["Skill"]:
        """获取技能。

        Args:
            name: 技能名称

        Returns:
            Skill 实例
        """
        if self._skill_registry is None:
            return None
        return self._skill_registry.get(name)

    def list_skills(self) -> List[str]:
        """列出所有已注册技能。"""
        if self._skill_registry is None:
            return []
        return self._skill_registry.list()

    def remove_skill(self, name: str) -> bool:
        """移除技能。

        Args:
            name: 技能名称

        Returns:
            是否成功移除
        """
        if self._skill_registry is None:
            return False

        result = self._skill_registry.unregister(name)
        if result:
            self._message_manager.remove_skill_prompt(name)

        return result

    def load_skills_from_directory(
        self,
        directory: str,
        recursive: bool = True,
    ) -> List["Skill"]:
        """从目录加载技能。

        Args:
            directory: 目录路径
            recursive: 是否递归扫描

        Returns:
            加载的技能列表
        """
        from agentforge.skills import SkillLoader

        loader = SkillLoader(self._skill_registry)
        skills = loader.discover_skills(directory, recursive, auto_register=True)

        # 注册所有技能的工具和提示
        for skill in skills:
            skill_tools = skill.get_tools()
            for tool in skill_tools:
                self.add_tool(tool)

            prompt_template = skill.get_prompt_template()
            if prompt_template:
                self._message_manager.add_skill_prompt(skill.name, prompt_template)

        return skills

    # === 生命周期 ===

    def on(
        self,
        event_type: EventType,
        callback: Callable,
        priority: int = 0,
    ) -> None:
        """注册事件监听器。

        Args:
            event_type: 事件类型
            callback: 回调函数
            priority: 优先级
        """
        self._event_dispatcher.on(event_type, callback, priority)

    def get_interrupt_token(self) -> InterruptToken:
        """获取中断令牌。

        Returns:
            InterruptToken 实例
        """
        return self._interrupt_handler.create_token()

    def run(
        self,
        message: Union[str, Message],
        max_iterations: int = 10,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> NormalizedResponse:
        """运行 Agent 对话。

        Args:
            message: 用户消息
            max_iterations: 最大迭代次数
            interrupt_token: 中断令牌（可选）

        Returns:
            最终响应
        """
        # 添加用户消息
        if isinstance(message, str):
            self._message_manager.add_user_message(message)
        else:
            self._message_manager.add_message(message)

        # 发射开始事件
        self._event_dispatcher.dispatch(EventType.AGENT_START, {})

        # 创建中断令牌
        if interrupt_token is None:
            interrupt_token = self._interrupt_handler.create_token()

        # 重置迭代预算
        self._iteration_budget.reset(max_iterations)

        # 重置护栏
        self._guardrails.reset_for_turn()
        self._execution_engine.reset_for_turn()

        interrupt_check = lambda: interrupt_token.check()

        iteration = 0
        while iteration < max_iterations and self._iteration_budget.remaining > 0:
            # 检查中断
            if interrupt_token.check():
                self._event_dispatcher.dispatch(
                    EventType.AGENT_INTERRUPT,
                    {"reason": interrupt_token.reason},
                )
                break

            # 获取上下文
            context = self._message_manager.get_context()

            # 使用执行引擎调用 Provider
            result = self._execution_engine.execute(
                messages=context,
                tools=self._tools,
                interrupt_check=interrupt_check,
                on_response=lambda r: self._event_dispatcher.dispatch(
                    EventType.PROVIDER_RESPONSE,
                    {"response": r},
                ),
                on_retry=lambda count, delay, classified: logger.warning(
                    f"重试 {count}/{self._settings.max_retries}: "
                    f"{classified.reason.value} - {classified.message}"
                ),
                on_fallback=lambda provider, model: logger.info(
                    f"激活回退: {provider}/{model}"
                ),
            )

            # 检查执行结果
            if result.interrupted:
                self._event_dispatcher.dispatch(
                    EventType.AGENT_INTERRUPT,
                    {"reason": interrupt_token.reason or "执行中断"},
                )
                break

            if result.failed:
                logger.error(f"执行失败: {result.error}")
                self._event_dispatcher.dispatch(EventType.AGENT_END, {})
                # 返回错误响应
                return NormalizedResponse(
                    content=f"执行失败: {result.error}",
                    tool_calls=None,
                    usage=None,
                    finish_reason="error",
                )

            response = result.response
            if response is None:
                break

            # 检查是否有工具调用
            if response.tool_calls:
                # 添加 assistant 消息
                self._message_manager.add_assistant_message(response)

                # 执行工具
                self._event_dispatcher.dispatch(
                    EventType.TOOL_START,
                    {"tool_calls": response.tool_calls},
                )

                tool_results = self._execution_engine.execute_tool_calls(
                    response=response,
                    tools=self._tools,
                    interrupt_check=interrupt_check,
                    on_tool_result=lambda r: logger.debug(
                        f"工具结果: {r.tool_call_id} - {r.content[:100] if r.content else 'empty'}"
                    ),
                )

                self._event_dispatcher.dispatch(
                    EventType.TOOL_END,
                    {"results": tool_results},
                )

                # 检查护栏是否阻止
                halt_decision = self._guardrails.halt_decision
                if halt_decision and halt_decision.should_halt:
                    logger.warning(f"护栏阻止: {halt_decision.message}")
                    self._event_dispatcher.dispatch(EventType.AGENT_END, {})
                    return NormalizedResponse(
                        content=f"护栏阻止: {halt_decision.message}",
                        tool_calls=None,
                        usage=None,
                        finish_reason="halt",
                    )

                # 添加工具结果
                self._message_manager.add_tool_results(tool_results)

                # 消耗迭代预算
                self._iteration_budget.consume()
                iteration += 1
                continue

            # 无工具调用，返回最终响应
            self._message_manager.add_assistant_message(response)

            self._event_dispatcher.dispatch(EventType.AGENT_END, {})
            return response

        # 达到最大迭代次数
        if iteration >= max_iterations:
            logger.warning(f"达到最大迭代次数: {max_iterations}")

        self._event_dispatcher.dispatch(EventType.AGENT_END, {})

        # 返回最后响应或空响应
        if result and result.response:
            return result.response

        return NormalizedResponse(
            content="达到最大迭代次数，未能完成任务",
            tool_calls=None,
            usage=None,
            finish_reason="max_iterations",
        )

    def stream(
        self,
        message: Union[str, Message],
        max_iterations: int = 10,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> Iterator[NormalizedResponse]:
        """流式运行 Agent 对话。

        Args:
            message: 用户消息
            max_iterations: 最大迭代次数
            interrupt_token: 中断令牌（可选）

        Yields:
            响应块
        """
        # 添加用户消息
        if isinstance(message, str):
            self._message_manager.add_user_message(message)
        else:
            self._message_manager.add_message(message)

        # 发射开始事件
        self._event_dispatcher.dispatch(EventType.AGENT_START, {})

        # 创建中断令牌
        if interrupt_token is None:
            interrupt_token = self._interrupt_handler.create_token()

        # 重置迭代预算
        self._iteration_budget.reset(max_iterations)
        self._guardrails.reset_for_turn()

        interrupt_check = lambda: interrupt_token.check()

        iteration = 0
        while iteration < max_iterations and self._iteration_budget.remaining > 0:
            # 检查中断
            if interrupt_token.check():
                self._event_dispatcher.dispatch(
                    EventType.AGENT_INTERRUPT,
                    {"reason": interrupt_token.reason},
                )
                break

            # 获取上下文
            context = self._message_manager.get_context()

            # 流式调用 Provider
            self._event_dispatcher.dispatch(EventType.PROVIDER_REQUEST, {})

            final_response = None
            try:
                for chunk in self._provider.stream(
                    messages=context,
                    tools=list(self._tools.values()) if self._tools else None,
                ):
                    self._event_dispatcher.dispatch(
                        EventType.STREAM_CHUNK,
                        {"chunk": chunk},
                    )
                    yield chunk
                    final_response = chunk

            except Exception as e:
                logger.error(f"流式调用失败: {e}")
                # 对于流式调用，暂时不实现完整重试
                yield NormalizedResponse(
                    content=f"流式调用错误: {e}",
                    tool_calls=None,
                    usage=None,
                    finish_reason="error",
                )
                break

            self._event_dispatcher.dispatch(EventType.STREAM_END, {})
            self._event_dispatcher.dispatch(
                EventType.PROVIDER_RESPONSE,
                {"response": final_response},
            )

            if final_response is None:
                break

            # 检查是否有工具调用
            if final_response.tool_calls:
                # 添加 assistant 消息
                self._message_manager.add_assistant_message(final_response)

                # 执行工具
                self._event_dispatcher.dispatch(
                    EventType.TOOL_START,
                    {"tool_calls": final_response.tool_calls},
                )

                tool_results = self._execution_engine.execute_tool_calls(
                    response=final_response,
                    tools=self._tools,
                    interrupt_check=interrupt_check,
                )

                self._event_dispatcher.dispatch(
                    EventType.TOOL_END,
                    {"results": tool_results},
                )

                # 添加工具结果
                self._message_manager.add_tool_results(tool_results)

                self._iteration_budget.consume()
                iteration += 1
                continue

            # 无工具调用，返回最终响应
            self._message_manager.add_assistant_message(final_response)
            self._event_dispatcher.dispatch(EventType.AGENT_END, {})
            break

    def clear(self) -> None:
        """清空消息历史。"""
        self._message_manager.clear()

    def shutdown(self) -> None:
        """关闭 Agent。

        同步记忆数据并清理资源。
        """
        # 同步记忆
        if self._memory_manager:
            try:
                sync_result = self._memory_manager.sync_all()
                logger.debug(f"记忆同步结果: {sync_result}")
            except Exception as e:
                logger.warning(f"同步记忆失败: {e}")

        # 清理技能
        if self._skill_registry:
            try:
                self._skill_registry.clear()
            except Exception as e:
                logger.debug(f"清理技能注册表失败: {e}")

        self._tool_orchestrator.shutdown()

    def __enter__(self) -> "Agent":
        """上下文管理器入口。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.shutdown()

    # === 活动追踪 ===

    def _touch_activity(self, desc: str) -> None:
        """更新活动状态（线程安全）。

        Args:
            desc: 活动描述
        """
        self._last_activity_ts = time.time()
        self._last_activity_desc = desc

    def _capture_rate_limit_state(self, http_response: Any) -> None:
        """从 HTTP 响应捕获速率限制状态。

        Args:
            http_response: HTTP 响应对象
        """
        if http_response is None:
            return
        headers = getattr(http_response, "headers", None)
        if not headers:
            return
        try:
            self._rate_limit_state = {
                "remaining": headers.get("x-ratelimit-remaining"),
                "reset": headers.get("x-ratelimit-reset"),
                "limit": headers.get("x-ratelimit-limit"),
            }
        except Exception:
            pass

    def get_activity_summary(self) -> Dict[str, Any]:
        """返回 Agent 当前活动状态摘要（用于诊断）。

        Returns:
            活动状态摘要
        """
        return {
            "last_activity_ts": self._last_activity_ts,
            "last_activity_desc": self._last_activity_desc,
            "seconds_since_activity": round(time.time() - self._last_activity_ts, 1),
            "api_call_count": self._api_call_count,
            "rate_limit_state": self._rate_limit_state,
        }