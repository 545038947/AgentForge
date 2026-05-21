"""工具类型定义。

定义工具规范和执行结果的结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolSpec:
    """工具规范定义。

    定义工具的元信息，用于向 LLM 描述工具能力。
    """
    name: str  # 工具名称（唯一标识）
    description: str  # 工具描述
    parameters: Dict[str, Any]  # JSON Schema 格式的参数定义

    # 可选属性
    timeout: float = 300.0  # 执行超时（秒）
    requires_approval: bool = False  # 是否需要审批
    dangerous: bool = False  # 是否为危险操作

    def to_openai_tool(self) -> Dict[str, Any]:
        """转换为 OpenAI 工具格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def to_anthropic_tool(self) -> Dict[str, Any]:
        """转换为 Anthropic 工具格式。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class ToolResult:
    """工具执行结果。

    封装工具执行的返回值和状态。
    """
    tool_call_id: str  # 对应的 ToolCall.id
    content: str  # 执行结果内容
    is_error: bool = False  # 是否为错误结果
    metadata: Optional[Dict[str, Any]] = field(default=None, repr=False)  # 额外元数据

    @property
    def success(self) -> bool:
        """检查是否执行成功。"""
        return not self.is_error

    def to_content_block(self) -> Dict[str, Any]:
        """转换为内容块格式。"""
        return {
            "type": "tool_result",
            "tool_use_id": self.tool_call_id,
            "content": self.content,
            "is_error": self.is_error,
        }


@dataclass
class Toolset:
    """工具集定义。

    将相关工具组织成集合，便于管理和加载。
    """
    name: str  # 工具集名称
    description: str  # 工具集描述
    tools: List[ToolSpec]  # 包含的工具列表

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """根据名称获取工具。"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """转换为 OpenAI 工具列表格式。"""
        return [tool.to_openai_tool() for tool in self.tools]

    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """转换为 Anthropic 工具列表格式。"""
        return [tool.to_anthropic_tool() for tool in self.tools]
