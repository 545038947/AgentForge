"""Agent 门面类。

整合所有组件，提供统一的 Agent 接口。
使用 ExecutionEngine 处理重试循环和错误恢复。
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import time
import weakref
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
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
from agentforge.tools.guardrails import ToolCallGuardrailController
from agentforge.types import Message, NormalizedResponse, ToolResult, StreamDelta, ToolCall
from agentforge.mcp.errors import MCPConnectionError
from agentforge.types.errors import ProviderError
from agentforge.types.messages import TextContent, ImageContent, ToolUseContent
from agentforge.core import (
    IterationBudget,
    FallbackChain,
    ExecutionEngine,
    ExecutionConfig,
    ExecutionResult,
    StreamAccumulator,
    AsyncIteratorWrapper,
)

if TYPE_CHECKING:
    from agentforge.providers import Provider
    from agentforge.memory import MemoryManager, MemoryProvider
    from agentforge.skills import Skill, SkillRegistry
    from agentforge.profiles import ProfileRegistry, ProviderRegistry

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
        # 简化方式（自动选择 Provider）
        agent = Agent(model="gpt-4", api_key="...")

        # 完整方式（显式 Provider）
        agent = Agent(provider=provider, settings=settings)

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
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        provider: Optional["Provider"] = None,
        settings: Optional[Settings] = None,
        tools: Optional[List[Union[Tool, Callable]]] = None,
        approval_callback: Optional[ApprovalCallback] = None,
        fallback_chain: Optional[FallbackChain] = None,
        memory_manager: Optional["MemoryManager"] = None,
        skill_registry: Optional["SkillRegistry"] = None,
        session_provider: Optional["SessionProvider"] = None,
        session_id: Optional[str] = None,
        profile_registry: Optional["ProfileRegistry"] = None,
        provider_registry: Optional["ProviderRegistry"] = None,
        register_atexit: bool = True,
    ):
        """初始化 Agent。

        支持两种初始化方式：

        1. 化方式（自动选择 Provider）：
           Agent(model="gpt-4", api_key="...")

        2. 完整方式（显式 Provider）：
           Agent(provider=provider, settings=settings)

        Args:
            model: 模型名称（简化方式）
            api_key: API 密钥（简化方式）
            provider: Provider 实例（完整方式）
            settings: 配置对象（可选）
            tools: 工具列表（可选）
            approval_callback: 审批回调（可选）
            fallback_chain: 回退链（可选）
            memory_manager: 记忆管理器（可选）
            skill_registry: 技能注册表（可选）
            session_provider: 会话提供者（可选，用于持久化）
            session_id: 会话 ID（可选，用于恢复会话）
            profile_registry: Profile 注册表（可选，用于专家 Agent）
            provider_registry: Provider 注册表（可选，用于专家 Agent）
        """
        # 自动选择 Provider
        if provider is None:
            provider = self._auto_select_provider(model, api_key)

        # 创建默认 Settings
        if settings is None:
            settings = Settings(model=model or "default")

        self._provider = provider
        self._settings = settings

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

        # 会话提供者
        self._session_provider = session_provider
        self._session_id = session_id

        # 如果提供了会话 ID 但没有 session_provider，创建默认的内存提供者
        if session_id and not session_provider:
            from agentforge.session import InMemorySessionProvider
            self._session_provider = InMemorySessionProvider()

        # 如果有会话 ID，创建或恢复会话
        if self._session_id and self._session_provider:
            existing = self._session_provider.get_session(self._session_id)
            if existing is None:
                # 创建新会话
                self._session_provider.create_session(
                    session_id=self._session_id,
                    source="agentforge",
                    model=model or getattr(provider, "_model", "unknown"),
                )
            else:
                # 恢复会话历史
                self._restore_session_history()

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

        # Profile 相关
        self._profile_registry = profile_registry
        self._provider_registry = provider_registry

        # Agent 状态追踪（用于诊断和监控）
        self._last_activity_ts: float = time.time()
        self._last_activity_desc: str = "初始化"
        self._rate_limit_state: Optional[Dict[str, Any]] = None
        self._api_call_count: int = 0

        # atexit 钩子注册
        self._atexit_registered: bool = False
        if register_atexit:
            self._register_atexit()

    def _restore_session_history(self) -> None:
        """从 SessionProvider 恢复会话历史。"""
        if not self._session_provider or not self._session_id:
            return

        messages = self._session_provider.get_messages(self._session_id)
        for msg in messages:
            if msg.role == "user":
                # 用户消息
                if isinstance(msg.content, str):
                    self._message_manager.add_user_message(msg.content)
                elif isinstance(msg.content, list):
                    # 多模态内容
                    content_blocks = []
                    for item in msg.content:
                        if item.get("type") == "text":
                            content_blocks.append(TextContent(text=item.get("text", "")))
                        elif item.get("type") == "image_url":
                            content_blocks.append(ImageContent(
                                url=item.get("image_url", {}).get("url", ""),
                            ))
                    if content_blocks:
                        self._message_manager.add_message(Message(role="user", content=content_blocks))
            elif msg.role == "assistant":
                # Assistant 消息
                content = []
                if isinstance(msg.content, str) and msg.content:
                    content.append(TextContent(text=msg.content))
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content.append(ToolUseContent(
                            id=tc.get("id", ""),
                            name=tc.get("function", {}).get("name", ""),
                            input=tc.get("function", {}).get("arguments", {}),
                        ))
                if content:
                    self._message_manager.add_message(Message(role="assistant", content=content))

    def _sync_to_session(self, role: str, content: Any, **kwargs) -> None:
        """同步消息到 SessionProvider。"""
        # 使用 getattr 安全访问，因为某些测试可能绕过 __init__
        session_provider = getattr(self, "_session_provider", None)
        session_id = getattr(self, "_session_id", None)
        if not session_provider or not session_id:
            return

        try:
            session_provider.append_message(
                session_id=session_id,
                role=role,
                content=content,
                **kwargs,
            )
        except (OSError, IOError) as e:
            logger.warning(f"同步消息到会话失败: {e}")

    def _sync_assistant_message(self, response: NormalizedResponse) -> None:
        """同步 assistant 消息到 SessionProvider。"""
        # 使用 getattr 安全访问，因为某些测试可能绕过 __init__
        session_provider = getattr(self, "_session_provider", None)
        session_id = getattr(self, "_session_id", None)
        if not session_provider or not session_id:
            return

        try:
            # 构建工具调用数据
            tool_calls_data = None
            if response.tool_calls:
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ]

            session_provider.append_message(
                session_id=session_id,
                role="assistant",
                content=response.content or "",
                tool_calls=tool_calls_data,
            )
        except (OSError, IOError) as e:
            logger.warning(f"同步 assistant 消息到会话失败: {e}")

    def get_session_id(self) -> Optional[str]:
        """获取当前会话 ID。"""
        return self._session_id

    def get_session_info(self) -> Optional[Any]:
        """获取当前会话信息。"""
        if not self._session_provider or not self._session_id:
            return None
        return self._session_provider.get_session(self._session_id)

    def set_session_title(self, title: str) -> bool:
        """设置当前会话标题。"""
        if not self._session_provider or not self._session_id:
            return False
        return self._session_provider.set_session_title(self._session_id, title)

    def validate_profiles(self) -> Dict[str, tuple]:
        """验证所有 Profile 的健康状态。

        Returns:
            {profile_name: (errors, warnings)}
        """
        if self._profile_registry is None:
            return {}
        return self._profile_registry.validate()

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

    def add_tools(self, tools: List[Union[Tool, Callable]]) -> List[Tool]:
        """批量添加工具。

        Args:
            tools: 工具实例或函数列表

        Returns:
            注册的 Tool 实例列表
        """
        return [self.add_tool(tool) for tool in tools]

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

    def enable_memory_store(
        self,
        base_path: Optional[str] = "./memories",
        store: Optional["MemoryStoreBase"] = None,
        memory_char_limit: int = 2200,
        user_char_limit: int = 1375,
    ) -> None:
        """启用 MemoryStore（长期记忆）。

        MemoryStore 用于存储持久化的记忆信息，包括：
        - MEMORY.md: 事实记忆（有界 2200 chars）
        - USER.md: 用户偏好（有界 1375 chars）

        支持两种方式：
        1. 传入 base_path：使用默认的 MemoryStore 实现
        2. 传入 store：使用自定义的 MemoryStoreBase 实现（如多用户存储）

        Args:
            base_path: 存储目录路径
            store: 自定义 MemoryStoreBase 实例（优先级高于 base_path）
            memory_char_limit: MEMORY 文件字符限制
            user_char_limit: USER 文件字符限制

        使用示例：
            # 使用默认存储
            agent = Agent(model="gpt-4")
            agent.enable_memory_store("./memories")

            # 使用自定义存储（如多用户）
            agent.enable_memory_store(
                store=MultiUserMemoryStore("./memories", user_id="user-123")
            )

            # 预取（加载 MemoryStore 并创建冻结快照）
            agent.prefetch()

            # 运行对话
            agent.run("记住我的名字是张三")

            # 同步（写入 MemoryStore）
            agent.sync()
        """
        if self._memory_manager is None:
            from agentforge.memory import MemoryManager
            self._memory_manager = MemoryManager(
                event_dispatcher=self._event_dispatcher,
            )

        self._memory_manager.enable_memory_store(
            base_path=base_path,
            store=store,
            memory_char_limit=memory_char_limit,
            user_char_limit=user_char_limit,
        )

    def get_memory_tools(self) -> List["Tool"]:
        """获取记忆工具列表。

        返回可以让 LLM 主动调用以保存和查询记忆的工具。

        Returns:
            记忆工具列表 [SaveMemoryTool, QueryMemoryTool]

        使用示例：
            agent = Agent(model="gpt-4")
            agent.enable_memory_store("./memories")

            # 获取记忆工具并添加到 Agent
            memory_tools = agent.get_memory_tools()
            agent.add_tools(memory_tools)

            # 现在 LLM 可以主动保存和查询记忆了
            agent.run("请记住我喜欢用 Python")
        """
        if self._memory_manager is None:
            logger.warning("MemoryManager 未初始化")
            return []

        from agentforge.tools.builtins.memory import (
            SaveMemoryTool,
            QueryMemoryTool,
        )

        return [
            SaveMemoryTool(self._memory_manager),
            QueryMemoryTool(self._memory_manager),
        ]

    def add_memory_entry(
        self,
        target: str,
        entry: str,
    ) -> bool:
        """添加记忆条目到 MemoryStore。

        Args:
            target: 目标类型（memory/user）
            entry: 条目内容

        Returns:
            是否成功添加
        """
        if self._memory_manager is None:
            return False

        return self._memory_manager.add_memory_entry(target, entry)

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
        会调用 MemoryManager.on_session_start() 触发冻结快照。

        Args:
            keys: 每个 provider 要预取的键列表

        Returns:
            预取结果
        """
        if self._memory_manager is None:
            return {}

        # 触发会话开始钩子（加载 MemoryStore 并创建冻结快照）
        self._memory_manager.on_session_start()

        result = self._memory_manager.prefetch_all(keys)

        # 将记忆信息添加到系统提示（包含冻结快照）
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

        # 触发会话开始钩子
        self._memory_manager.on_session_start()

        result = await self._memory_manager.prefetch_all_async(keys)

        memory_prompt = self._memory_manager.build_system_prompt()
        if memory_prompt:
            self._message_manager.add_memory_context(memory_prompt)

        return result

    def sync(self) -> Dict[str, int]:
        """同步记忆数据。

        将缓存中的数据写回 provider。
        会调用 MemoryManager.on_session_end() 同步 MemoryStore。

        Returns:
            每个 provider 同步的条目数
        """
        if self._memory_manager is None:
            return {}

        result = self._memory_manager.sync_all()

        # 触发会话结束钩子（同步 MemoryStore 并刷新快照）
        self._memory_manager.on_session_end()

        return result

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

    # === MCP 管理 ===

    def add_mcp_servers(self, config_path: str) -> None:
        """从 YAML 配置文件添加 MCP Servers。

        Args:
            config_path: YAML 配置文件路径

        使用示例：
            agent = Agent(model="gpt-4")
            agent.add_mcp_servers("./mcp_config.yaml")

            # 预取记忆和 MCP 工具
            agent.prefetch()

            # 运行对话（MCP 工具自动注册）
            response = agent.run("使用工具帮我完成任务")
        """
        from agentforge.mcp import MCPManager
        import asyncio

        if not hasattr(self, "_mcp_manager") or self._mcp_manager is None:
            self._mcp_manager = MCPManager()

        # 使用线程池执行异步初始化，避免事件循环冲突
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                self._mcp_manager.initialize_from_yaml(config_path)
            )
            future.result(timeout=60)  # 等待完成，最多 60 秒

        # 注册所有 MCP 工具到 Agent
        for tool in self._mcp_manager.get_all_tools():
            self.add_tool(tool)

    def add_mcp_servers_from_dict(self, config_data: dict) -> None:
        """从字典配置添加 MCP Servers。

        Args:
            config_data: MCP 配置字典

        使用示例：
            agent = Agent(model="gpt-4")
            agent.add_mcp_servers_from_dict({
                "servers": {
                    "my-server": {
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "my_mcp_server"]
                    }
                }
            })
        """
        from agentforge.mcp import MCPManager
        import asyncio

        if not hasattr(self, "_mcp_manager") or self._mcp_manager is None:
            self._mcp_manager = MCPManager()

        # 使用线程池执行异步初始化，避免事件循环冲突
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                self._mcp_manager.initialize_from_dict(config_data)
            )
            future.result(timeout=60)

        for tool in self._mcp_manager.get_all_tools():
            self.add_tool(tool)

    def get_mcp_manager(self) -> Optional["MCPManager"]:
        """获取 MCP Manager 实例。"""
        return getattr(self, "_mcp_manager", None)

    def get_mcp_tools(self) -> List["Tool"]:
        """获取所有已注册的 MCP 工具。"""
        if not hasattr(self, "_mcp_manager") or self._mcp_manager is None:
            return []
        return self._mcp_manager.get_all_tools()

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
            self._sync_to_session("user", message)
        else:
            self._message_manager.add_message(message)
            self._sync_to_session("user", message.content if hasattr(message, 'content') else str(message))

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
                # 同步 assistant 消息到会话
                self._sync_assistant_message(response)

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
            # 同步 assistant 消息到会话
            self._sync_assistant_message(response)

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
            self._sync_to_session("user", message)
        else:
            self._message_manager.add_message(message)
            self._sync_to_session("user", message.content if hasattr(message, 'content') else str(message))

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

            # 累积流式响应
            accumulated_content = ""
            accumulated_tool_calls: List[ToolCall] = []
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

                    # 累积内容
                    if chunk.content:
                        accumulated_content += chunk.content

                    # 累积工具调用
                    if chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            # 检查是否已存在相同 id 的工具调用
                            existing = None
                            for existing_tc in accumulated_tool_calls:
                                if existing_tc.id == tc.id:
                                    existing = existing_tc
                                    break

                            if existing:
                                # 累积 arguments
                                if tc.arguments:
                                    # 使用 dataclass 的不可变性，创建新对象
                                    idx = accumulated_tool_calls.index(existing)
                                    accumulated_tool_calls[idx] = ToolCall(
                                        id=existing.id,
                                        name=existing.name or tc.name,
                                        arguments=existing.arguments + tc.arguments,
                                        provider_data=existing.provider_data or tc.provider_data,
                                    )
                            else:
                                accumulated_tool_calls.append(tc)

                    yield chunk
                    final_response = chunk

            except (ProviderError, OSError, ConnectionError, TimeoutError, RuntimeError) as e:
                logger.error(f"流式调用失败: {e}")
                # 对于流式调用，暂时不实现完整重试
                yield NormalizedResponse(
                    content=f"流式调用错误: {e}",
                    tool_calls=None,
                    usage=None,
                    finish_reason="error",
                )
                break

            # 构建累积后的最终响应
            if final_response is not None:
                final_response = NormalizedResponse(
                    content=accumulated_content,
                    tool_calls=accumulated_tool_calls if accumulated_tool_calls else None,
                    finish_reason=final_response.finish_reason,
                    usage=final_response.usage,
                )

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
                # 同步 assistant 消息到会话
                self._sync_assistant_message(final_response)

                # 执行工具
                self._event_dispatcher.dispatch(
                    EventType.TOOL_START,
                    {"tool_calls": final_response.tool_calls},
                )

                # 构建工具调用信息
                tool_names = [tc.name for tc in final_response.tool_calls]
                tool_info = ", ".join(tool_names)
                logger.info(f"执行工具: {tool_info}")

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

                # 记录工具结果到日志
                for result in tool_results:
                    status = "失败" if result.is_error else "成功"
                    logger.info(f"工具 {result.tool_call_id} {status}")

                self._iteration_budget.consume()
                iteration += 1
                continue

            # 无工具调用，返回最终响应
            self._message_manager.add_assistant_message(final_response)
            # 同步 assistant 消息到会话
            self._sync_assistant_message(final_response)
            self._event_dispatcher.dispatch(EventType.AGENT_END, {})
            break

    def stream_deltas(
        self,
        message: Union[str, Message],
        max_iterations: int = 10,
        interrupt_token: Optional[InterruptToken] = None,
        include_reasoning: bool = False,
        suppress_tool_text: bool = True,
    ) -> Iterator[StreamDelta]:
        """流式运行 Agent，返回 Token 增量。

        与 stream() 不同，此方法返回每个 Token 增量，
        适用于需要实时显示响应的场景（如 CLI、Web UI）。

        Args:
            message: 用户消息
            max_iterations: 最大迭代次数
            interrupt_token: 中断令牌（可选）
            include_reasoning: 是否包含推理增量
            suppress_tool_text: 当有工具调用时是否抑制文本流式
                               （避免 "我将使用工具..." 文本与工具调用一起显示）

        Yields:
            StreamDelta 增量对象，包含 content、reasoning 等

        使用示例：
            for delta in agent.stream_deltas("你好"):
                if delta.has_content:
                    print(delta.content, end="", flush=True)
                if delta.is_final:
                    print()  # 换行
        """
        # 添加用户消息
        if isinstance(message, str):
            self._message_manager.add_user_message(message)
            self._sync_to_session("user", message)
        else:
            self._message_manager.add_message(message)
            self._sync_to_session("user", message.content if hasattr(message, 'content') else str(message))

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
                yield StreamDelta(
                    content=f"\n[中断: {interrupt_token.reason}]",
                    finish_reason="interrupt",
                )
                break

            # 获取上下文
            context = self._message_manager.get_context()

            # 流式调用 Provider
            self._event_dispatcher.dispatch(EventType.PROVIDER_REQUEST, {})

            # 使用 StreamAccumulator 管理流式累积
            accumulator = StreamAccumulator()

            try:
                for chunk in self._provider.stream(
                    messages=context,
                    tools=list(self._tools.values()) if self._tools else None,
                ):
                    # 处理文本内容增量
                    delta_content = accumulator.add_content(chunk.content)

                    # 处理推理内容增量
                    delta_reasoning = ""
                    if include_reasoning:
                        delta_reasoning = accumulator.add_reasoning(chunk.reasoning)

                    # 处理工具调用增量
                    # 注意：某些 Provider（如 OpenAI SDK）在流式响应中返回完整的 tool_calls
                    # 而不是增量式的。我们需要检查是否需要处理增量式工具调用。
                    if chunk.tool_calls:
                        # 对于非增量式工具调用，直接使用
                        accumulator.tool_calls.calls = {
                            i: {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": tc.name, "arguments": tc.arguments},
                                "extra_content": tc.provider_data.get("extra_content") if tc.provider_data else None,
                            }
                            for i, tc in enumerate(chunk.tool_calls)
                        }
                        accumulator.tool_calls.notified_names = set(range(len(chunk.tool_calls)))

                    # 更新使用统计和结束原因
                    accumulator.update_usage(chunk.usage)
                    accumulator.update_finish_reason(chunk.finish_reason)
                    accumulator.update_model(chunk.model)

                    # 决定是否发射文本增量
                    # 当有工具调用且 suppress_tool_text 为 True 时，抑制文本流式
                    should_emit_text = delta_content and not (
                        suppress_tool_text and accumulator.should_suppress_text_streaming()
                    )

                    # 发射推理增量事件
                    if delta_reasoning:
                        self._event_dispatcher.dispatch(
                            EventType.STREAM_REASONING_DELTA,
                            {"reasoning": delta_reasoning},
                        )

                    # 发射文本增量事件
                    if should_emit_text:
                        self._event_dispatcher.dispatch(
                            EventType.STREAM_DELTA,
                            {"content": delta_content},
                        )

                    # 只在有增量时才 yield
                    if should_emit_text or delta_reasoning:
                        yield StreamDelta(
                            content=delta_content if should_emit_text else "",
                            reasoning=delta_reasoning,
                        )

            except (ProviderError, OSError, ConnectionError, TimeoutError, RuntimeError) as e:
                logger.error(f"流式调用失败: {e}")
                yield StreamDelta(
                    content=f"\n[错误: {e}]",
                    finish_reason="error",
                )
                break

            self._event_dispatcher.dispatch(EventType.STREAM_END, {})

            # 检查是否有工具调用
            if accumulator.has_tool_calls():
                # 构建完整响应
                final_response = accumulator.build_response()

                # 添加 assistant 消息
                self._message_manager.add_assistant_message(final_response)
                # 同步 assistant 消息到会话
                self._sync_assistant_message(final_response)

                # 发射工具调用生成事件
                tool_calls = final_response.tool_calls
                self._event_dispatcher.dispatch(
                    EventType.TOOL_GENERATED,
                    {"tool_calls": tool_calls},
                )

                # 执行工具
                self._event_dispatcher.dispatch(
                    EventType.TOOL_START,
                    {"tool_calls": tool_calls},
                )

                # 发射工具执行提示
                yield StreamDelta(
                    content="\n[执行工具...]",
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

                # 显示工具执行结果摘要
                for result in tool_results:
                    if result.is_error:
                        yield StreamDelta(
                            content=f"\n[工具 {result.tool_name} 错误]",
                        )
                    else:
                        yield StreamDelta(
                            content=f"\n[工具 {result.tool_name} 完成]",
                        )

                # 添加工具结果
                self._message_manager.add_tool_results(tool_results)

                self._iteration_budget.consume()
                iteration += 1
                continue

            # 无工具调用，返回最终增量
            final_response = accumulator.build_response()

            self._message_manager.add_assistant_message(final_response)
            # 同步 assistant 消息到会话
            self._sync_assistant_message(final_response)

            # 发射最终增量
            yield StreamDelta(
                content="",  # 内容已在前面的增量中发送
                finish_reason=accumulator.finish_reason or "stop",
                usage=accumulator.usage,
            )

            self._event_dispatcher.dispatch(EventType.AGENT_END, {})
            break

    def clear(self) -> None:
        """清空消息历史。"""
        self._message_manager.clear()

    def shutdown(self) -> None:
        """关闭 Agent。

        同步记忆数据并清理资源。
        """
        # 防止重复关闭
        if not hasattr(self, '_shutdown_done'):
            self._shutdown_done = False
        if self._shutdown_done:
            return
        self._shutdown_done = True

        # 同步记忆
        if self._memory_manager:
            try:
                sync_result = self._memory_manager.sync_all()
                logger.debug(f"记忆同步结果: {sync_result}")
            except (OSError, IOError) as e:
                logger.warning(f"同步记忆失败: {e}")

        # 关闭 MCP Servers
        if hasattr(self, "_mcp_manager") and self._mcp_manager:
            try:
                import asyncio
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._mcp_manager.shutdown()
                    )
                    future.result(timeout=10)
            except (OSError, MCPConnectionError) as e:
                logger.warning(f"关闭 MCP Servers 失败: {e}")

        # 清理技能
        if self._skill_registry:
            try:
                self._skill_registry.clear()
            except (OSError, RuntimeError) as e:
                logger.debug(f"清理技能注册表失败: {e}")

        self._tool_orchestrator.shutdown()

    def __enter__(self) -> "Agent":
        """上下文管理器入口。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.shutdown()

    def _register_atexit(self) -> None:
        """注册 atexit 钩子，确保进程退出时清理资源。"""
        # 使用弱引用避免阻止 Agent 被垃圾回收
        weak_self = weakref.ref(self)

        def atexit_callback():
            agent = weak_self()
            if agent is not None:
                try:
                    agent.shutdown()
                except (OSError, RuntimeError):
                    pass

        try:
            atexit.register(atexit_callback)
            self._atexit_registered = True
        except (RuntimeError, OSError):
            self._atexit_registered = False

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
        except (KeyError, TypeError, ValueError):
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

    # === 异步 API ===

    async def run_async(
        self,
        message: Union[str, Message],
        max_iterations: int = 10,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> NormalizedResponse:
        """异步运行 Agent。

        使用 asyncio.to_thread 包装同步调用，适用于异步上下文。

        Args:
            message: 用户消息
            max_iterations: 最大迭代次数
            interrupt_token: 中断令牌（可选）

        Returns:
            完整响应

        使用示例：
            response = await agent.run_async("你好")
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run(message, max_iterations, interrupt_token),
        )

    async def stream_async(
        self,
        message: Union[str, Message],
        max_iterations: int = 10,
        interrupt_token: Optional[InterruptToken] = None,
    ) -> AsyncIterator[NormalizedResponse]:
        """异步流式运行 Agent。

        Args:
            message: 用户消息
            max_iterations: 最大迭代次数
            interrupt_token: 中断令牌（可选）

        Yields:
            NormalizedResponse 响应块

        使用示例：
            async for chunk in agent.stream_async("你好"):
                print(chunk.content)
        """
        loop = asyncio.get_running_loop()
        sync_iterator = await loop.run_in_executor(
            None,
            lambda: self.stream(message, max_iterations, interrupt_token),
        )

        while True:
            chunk = await loop.run_in_executor(None, lambda: next(sync_iterator, None))
            if chunk is None:
                break
            yield chunk

    async def stream_deltas_async(
        self,
        message: Union[str, Message],
        max_iterations: int = 10,
        interrupt_token: Optional[InterruptToken] = None,
        include_reasoning: bool = False,
        suppress_tool_text: bool = True,
    ) -> AsyncIterator[StreamDelta]:
        """异步流式运行 Agent，返回 Token 增量。

        Args:
            message: 用户消息
            max_iterations: 最大迭代次数
            interrupt_token: 中断令牌（可选）
            include_reasoning: 是否包含推理增量
            suppress_tool_text: 当有工具调用时是否抑制文本流式

        Yields:
            StreamDelta 增量对象

        使用示例：
            async for delta in agent.stream_deltas_async("你好"):
                if delta.has_content:
                    print(delta.content, end="", flush=True)
        """
        loop = asyncio.get_running_loop()
        sync_iterator = await loop.run_in_executor(
            None,
            lambda: self.stream_deltas(
                message,
                max_iterations,
                interrupt_token,
                include_reasoning,
                suppress_tool_text,
            ),
        )

        while True:
            delta = await loop.run_in_executor(None, lambda: next(sync_iterator, None))
            if delta is None:
                break
            yield delta

    async def complete_async(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
    ) -> NormalizedResponse:
        """异步完成单次 API 调用（不执行工具循环）。

        适用于需要直接调用 Provider 的场景。

        Args:
            messages: 消息列表
            tools: 工具列表（可选）

        Returns:
            Provider 响应
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._provider.complete(
                messages=messages,
                tools=tools or list(self._tools.values()),
            ),
        )

    # === Provider 自动选择 ===

    @staticmethod
    def _auto_select_provider(
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> "Provider":
        """自动选择可用的 Provider。

        从已注册的 Profile 中选择有 API Key 配置的 Provider。
        如果指定了 model，尝试匹配 Profile 的模型列表或别名。

        Args:
            model: 模型名称（可选）
            api_key: API 密钥（可选）

        Returns:
            Provider 实例

        Raises:
            ConfigurationError: 没有可用的 Provider
        """
        from agentforge.providers.profile import get_profile, list_profiles
        from agentforge.providers.registry import ProviderRegistry
        from agentforge.types.errors import ConfigurationError

        profiles = list_profiles()

        # 收集可用的 Provider（有 API Key）
        available = []
        for name in profiles:
            profile = get_profile(name)
            if profile:
                key = api_key or profile.get_api_key()
                if key:
                    available.append((name, profile))

        if not available:
            raise ConfigurationError(
                "没有可用的 Provider，请配置 API Key 环境变量",
                details={
                    "hint": "设置 OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, MOONSHOT_API_KEY, DASHSCOPE_API_KEY 等",
                    "available_profiles": list(profiles),
                },
            )

        # 如果指定了 model，尝试匹配
        if model:
            model_lower = model.lower()
            for name, profile in available:
                # 检查模型列表
                for m in profile.fallback_models:
                    if model_lower.startswith(m.lower()) or m.lower().startswith(model_lower):
                        return ProviderRegistry.create(name, api_key=api_key or profile.get_api_key())

                # 检查 aliases
                for alias in profile.aliases:
                    if model_lower.startswith(alias.lower()):
                        return ProviderRegistry.create(name, api_key=api_key or profile.get_api_key())

        # 返回第一个可用的
        name, profile = available[0]
        logger.info(f"自动选择 Provider: {name}")
        return ProviderRegistry.create(name, api_key=api_key or profile.get_api_key())


# === 便捷函数 ===

def quick_chat(
    message: str,
    model: str = "gpt-4",
    api_key: Optional[str] = None,
    **kwargs,
) -> str:
    """单次对话便捷函数。

    适用于简单场景，不需要管理 Agent 生命周期。
    自动选择 Provider 并返回文本响应。

    Args:
        message: 用户消息
        model: 模型名称
        api_key: API 密钥（可选，从环境变量获取）
        **kwargs: 其他 Agent 参数

    Returns:
        响应文本内容

    使用示例：
        response = quick_chat("你好", model="deepseek-chat")
    """
    agent = Agent(model=model, api_key=api_key, **kwargs)
    response = agent.run(message)
    return response.content or ""