"""MCP Tool 包装器 - 将 MCP 工具转换为 AgentForge Tool。"""

import asyncio
import concurrent.futures
import threading
from typing import Any, Dict, Optional

from agentforge.tools.base import Tool
from agentforge.types import ToolResult
from agentforge.types.errors import ToolExecutionError
from agentforge.mcp.client import MCPClient
from agentforge.mcp.types import MCPToolSchema


class MCPTool(Tool):
    """将 MCP 工具包装为 AgentForge Tool。

    由于 MCP Client 使用 asyncio subprocess，而 Agent 的工具执行可能是同步的，
    这个类提供了在独立线程中运行异步代码的能力。
    """

    def __init__(self, client: MCPClient, schema: MCPToolSchema):
        """
        初始化 MCP Tool。

        Args:
            client: MCP Client 实例
            schema: MCP 工具 Schema
        """
        self._client = client
        self._schema = schema

    # === Tool 抽象属性 ===

    @property
    def name(self) -> str:
        """工具名称。"""
        return self._schema.name

    @property
    def description(self) -> str:
        """工具描述。"""
        return self._schema.description

    @property
    def parameters(self) -> Dict[str, Any]:
        """工具参数定义。"""
        return self._schema.inputSchema

    # === Tool 执行 ===

    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        """
        执行 MCP 工具调用。

        使用独立线程和新的事件循环来避免与主事件循环冲突。

        Args:
            tool_call_id: 工具调用 ID
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        try:
            # 在独立线程中运行，使用新的事件循环
            result_content = None
            result_error = None

            def run_in_thread():
                nonlocal result_content, result_error
                try:
                    # 创建新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # 复用已有的 client 连接，但需要在新循环中重新连接
                        # 或者直接在这里进行工具调用
                        result_content = loop.run_until_complete(
                            self._execute_with_new_connection(**kwargs)
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    result_error = e

            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()
            thread.join(timeout=self.timeout)

            if thread.is_alive():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"工具执行超时 ({self.timeout}s)",
                    is_error=True,
                )

            if result_error:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=str(result_error),
                    is_error=True,
                )

            return ToolResult(
                tool_call_id=tool_call_id,
                content=result_content,
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=str(e),
                is_error=True,
            )

    async def _execute_with_new_connection(self, **kwargs) -> str:
        """在新事件循环中创建新连接并执行工具调用。"""
        from agentforge.mcp.config import MCPServerConfig
        from agentforge.mcp.client import MCPClient

        # 获取原始配置
        config = self._client.config

        # 创建新的 client 和连接
        new_client = MCPClient(config)
        try:
            await new_client.connect()
            result = await new_client.call_tool(self.name, kwargs)

            if result.isError:
                raise ToolExecutionError(
                    f"MCP tool error: {result.content}",
                    tool_name=self.name,
                )

            return result.content
        finally:
            await new_client.disconnect()

    # === 辅助方法 ===

    def get_schema(self) -> Dict[str, Any]:
        """获取工具 Schema（用于 LLM 调用）。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """
        验证参数是否符合 Schema。

        Args:
            params: 待验证参数

        Returns:
            参数是否有效
        """
        required = self.parameters.get("required", [])
        for field in required:
            if field not in params:
                return False

        return True

    def __repr__(self) -> str:
        return f"MCPTool(name={self.name}, client={self._client.name})"
