"""Agent 门面类。

整合所有组件，提供统一的 Agent 接口。
"""

from __future__ import annotations

import logging
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
from agentforge.types import Message, NormalizedResponse

if TYPE_CHECKING:
    from agentforge.providers import Provider

logger = logging.getLogger(__name__)


class Agent:
    """Agent 门面类。

    整合所有组件，提供统一的 Agent 接口。

    组件：
    - MessageManager: 消息历史管理
    - ToolOrchestrator: 工具执行编排
    - EventDispatcher: 事件分发
    - InterruptHandler: 中断处理

    使用示例：
        agent = Agent(provider, settings)

        # 添加工具
        @agent.tool
        def search(query: str) -> str:
            return f"Results for {query}"

        # 运行对话
        response = agent.run("你好")

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
    ):
        """初始化 Agent。

        Args:
            provider: Provider 实例
            settings: 配置对象（可选）
            tools: 工具列表（可选）
            approval_callback: 审批回调（可选）
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

        # 工具注册表
        self._tools: Dict[str, Tool] = {}

        # 注册工具
        if tools:
            for t in tools:
                self.add_tool(t)

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

        iteration = 0
        while iteration < max_iterations:
            # 检查中断
            if interrupt_token.check():
                self._event_dispatcher.dispatch(
                    EventType.AGENT_INTERRUPT,
                    {"reason": interrupt_token.reason},
                )
                break

            # 获取上下文
            context = self._message_manager.get_context()

            # 调用 Provider
            self._event_dispatcher.dispatch(EventType.PROVIDER_REQUEST, {})
            response = self._provider.complete(
                messages=context,
                tools=list(self._tools.values()) if self._tools else None,
            )
            self._event_dispatcher.dispatch(
                EventType.PROVIDER_RESPONSE,
                {"response": response},
            )

            # 检查是否有工具调用
            if response.tool_calls:
                # 添加 assistant 消息
                self._message_manager.add_assistant_message(response)

                # 执行工具
                self._event_dispatcher.dispatch(
                    EventType.TOOL_START,
                    {"tool_calls": response.tool_calls},
                )

                tool_results = self._tool_orchestrator.execute(
                    tool_calls=response.tool_calls,
                    tools=self._tools,
                    interrupt_token=interrupt_token,
                )

                self._event_dispatcher.dispatch(
                    EventType.TOOL_END,
                    {"results": tool_results},
                )

                # 添加工具结果
                self._message_manager.add_tool_results(tool_results)

                iteration += 1
                continue

            # 无工具调用，返回最终响应
            self._message_manager.add_assistant_message(response)

            self._event_dispatcher.dispatch(EventType.AGENT_END, {})
            return response

        # 达到最大迭代次数
        logger.warning(f"达到最大迭代次数: {max_iterations}")
        self._event_dispatcher.dispatch(EventType.AGENT_END, {})
        return response

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

        iteration = 0
        while iteration < max_iterations:
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

                tool_results = self._tool_orchestrator.execute(
                    tool_calls=final_response.tool_calls,
                    tools=self._tools,
                    interrupt_token=interrupt_token,
                )

                self._event_dispatcher.dispatch(
                    EventType.TOOL_END,
                    {"results": tool_results},
                )

                # 添加工具结果
                self._message_manager.add_tool_results(tool_results)

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
        """关闭 Agent。"""
        self._tool_orchestrator.shutdown()

    def __enter__(self) -> "Agent":
        """上下文管理器入口。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.shutdown()
