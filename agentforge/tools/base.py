"""Tool 抽象基类。

定义工具的统一接口，支持函数装饰器创建工具。
"""

from __future__ import annotations

import functools
import inspect
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from agentforge.types import ToolSpec, ToolResult


class Tool(ABC):
    """Tool 抽象基类，定义工具接口。

    工具是 Agent 可以调用的功能单元，具有：
    - 元信息：name, description, parameters
    - 执行逻辑：execute 方法
    - 行为配置：timeout, requires_approval

    使用示例：
        class SearchTool(Tool):
            @property
            def name(self) -> str:
                return "search"

            @property
            def description(self) -> str:
                return "Search the web"

            @property
            def parameters(self) -> dict:
                return {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"]
                }

            def execute(self, tool_call_id: str, query: str) -> ToolResult:
                # 执行搜索
                return ToolResult(tool_call_id=tool_call_id, content="results...")
    """

    # ── 必须实现的抽象属性/方法 ──────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（唯一标识）。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述。"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """工具参数定义（JSON Schema 格式）。"""
        ...

    @abstractmethod
    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        """执行工具。

        Args:
            tool_call_id: 工具调用 ID
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        ...

    # ── 可选属性 ──────────────────────────────────────────────

    timeout: float = 300.0  # 执行超时（秒）
    requires_approval: bool = False  # 是否需要审批
    dangerous: bool = False  # 是否为危险操作

    def validate_args(self, **kwargs) -> Optional[str]:
        """验证参数。

        Args:
            **kwargs: 工具参数

        Returns:
            错误消息（如果验证失败），None 表示验证通过
        """
        return None

    def should_approve(self, args: Dict[str, Any]) -> bool:
        """判断是否需要审批。

        Args:
            args: 工具参数

        Returns:
            True 如果需要审批
        """
        return self.requires_approval

    def to_spec(self) -> ToolSpec:
        """转换为 ToolSpec。"""
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            timeout=self.timeout,
            requires_approval=self.requires_approval,
            dangerous=self.dangerous,
        )


class FunctionTool(Tool):
    """基于函数的工具实现。

    将普通 Python 函数包装为 Tool 实例。

    使用示例：
        @tool
        def search(query: str) -> str:
            '''Search the web.'''
            return "results..."

        # 或者
        def my_func(x: int) -> str:
            return str(x)

        tool = FunctionTool(my_func, name="my_tool", description="My tool")
    """

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: float = 300.0,
        requires_approval: bool = False,
    ):
        """初始化 FunctionTool。

        Args:
            func: 要包装的函数
            name: 工具名称（默认使用函数名）
            description: 工具描述（默认使用函数 docstring）
            parameters: 参数定义（默认从函数签名推断）
            timeout: 执行超时
            requires_approval: 是否需要审批
        """
        self._func = func
        self._name = name or func.__name__
        self._description = description or (func.__doc__ or "").strip()
        self._parameters = parameters or self._infer_parameters(func)
        self.timeout = timeout
        self.requires_approval = requires_approval

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> Dict[str, Any]:
        return self._parameters

    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        """执行函数。"""
        try:
            result = self._func(**kwargs)

            # 处理不同类型的返回值
            if isinstance(result, ToolResult):
                return result
            elif isinstance(result, str):
                return ToolResult(tool_call_id=tool_call_id, content=result)
            elif isinstance(result, dict):
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=json.dumps(result, ensure_ascii=False),
                )
            else:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=str(result),
                )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"工具执行错误: {e}",
                is_error=True,
            )

    def _infer_parameters(self, func: Callable) -> Dict[str, Any]:
        """从函数签名推断参数定义。"""
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            # 推断类型
            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                if param.annotation in (int, float):
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation in (list, List):
                    param_type = "array"
                elif param.annotation in (dict, Dict):
                    param_type = "object"

            properties[param_name] = {"type": param_type}

            # 没有默认值的参数是必需的
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        result = {
            "type": "object",
            "properties": properties,
        }
        if required:
            result["required"] = required

        return result


def tool(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    timeout: float = 300.0,
    requires_approval: bool = False,
) -> Union[Callable, FunctionTool]:
    """工具装饰器，将函数转换为 Tool。

    使用示例：
        @tool
        def search(query: str) -> str:
            '''Search the web.'''
            return "results..."

        @tool(name="my_search", requires_approval=True)
        def custom_search(q: str) -> str:
            return "..."
    """
    def decorator(f: Callable) -> FunctionTool:
        return FunctionTool(
            f,
            name=name,
            description=description,
            parameters=parameters,
            timeout=timeout,
            requires_approval=requires_approval,
        )

    if func is not None:
        # 直接调用 @tool（无参数）
        return decorator(func)
    else:
        # 带参数调用 @tool(...)
        return decorator


class ToolRegistry:
    """工具注册表。

    管理工具的注册、发现和创建。
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._lock = threading.Lock()

    def register(self, tool: Tool) -> None:
        """注册工具。

        Args:
            tool: Tool 实例
        """
        with self._lock:
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """取消注册工具。

        Args:
            name: 工具名称

        Returns:
            True 如果成功移除
        """
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                return True
            return False

    def get(self, name: str) -> Optional[Tool]:
        """获取工具。

        Args:
            name: 工具名称

        Returns:
            Tool 实例，如果不存在则返回 None
        """
        return self._tools.get(name)

    def list(self) -> List[str]:
        """列出所有已注册工具名称。"""
        return list(self._tools.keys())

    def get_all(self) -> Dict[str, Tool]:
        """获取所有工具。"""
        return self._tools.copy()

    def to_specs(self) -> List[ToolSpec]:
        """转换为 ToolSpec 列表。"""
        return [tool.to_spec() for tool in self._tools.values()]

    def clear(self) -> None:
        """清空注册表。"""
        with self._lock:
            self._tools.clear()


# 全局工具注册表
_global_registry = ToolRegistry()


def register_tool(tool: Tool) -> None:
    """注册工具到全局注册表。"""
    _global_registry.register(tool)


def get_tool(name: str) -> Optional[Tool]:
    """从全局注册表获取工具。"""
    return _global_registry.get(name)


def list_tools() -> List[str]:
    """列出全局注册表中的所有工具。"""
    return _global_registry.list()
