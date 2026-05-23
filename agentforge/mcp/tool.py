"""MCP Tool 包装器 - 将 MCP 工具转换为 AgentForge Tool。"""

from typing import Any, Dict, Optional

from agentforge.tools.base import Tool
from agentforge.types import ToolResult
from agentforge.types.errors import ToolExecutionError
from agentforge.mcp.client import MCPClient
from agentforge.mcp.types import MCPToolSchema


class MCPTool(Tool):
    """将 MCP 工具包装为 AgentForge Tool。"""

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
        执行 MCP 工具调用（同步包装器）。

        Args:
            tool_call_id: 工具调用 ID
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        import asyncio

        try:
            # 尝试在现有事件循环中运行
            try:
                loop = asyncio.get_running_loop()
                # 已在异步上下文中，创建任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._execute_async(**kwargs)
                    )
                    content = future.result(timeout=self.timeout)
            except RuntimeError:
                # 不在异步上下文中，创建新的事件循环
                content = asyncio.run(self._execute_async(**kwargs))

            return ToolResult(
                tool_call_id=tool_call_id,
                content=content,
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=str(e),
                is_error=True,
            )

    async def _execute_async(self, **kwargs) -> str:
        """异步执行 MCP 工具调用。"""
        try:
            result = await self._client.call_tool(self.name, kwargs)

            if result.isError:
                raise ToolExecutionError(f"MCP tool error: {result.content}")

            return result.content

        except Exception as e:
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError(f"Failed to call MCP tool: {e}") from e

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
