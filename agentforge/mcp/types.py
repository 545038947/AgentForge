"""MCP 类型定义。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MCPToolSchema:
    """MCP 工具 Schema。"""
    name: str
    description: str
    inputSchema: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict) -> "MCPToolSchema":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            inputSchema=data.get("inputSchema", {"type": "object"}),
        )


@dataclass
class MCPResourceSchema:
    """MCP 资源 Schema。"""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "MCPResourceSchema":
        return cls(
            uri=data["uri"],
            name=data.get("name", data["uri"]),
            description=data.get("description"),
            mimeType=data.get("mimeType"),
        )


@dataclass
class MCPToolResult:
    """MCP 工具调用结果。"""
    content: str
    isError: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "MCPToolResult":
        content = data.get("content", "")
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            content = "\n".join(texts)
        return cls(content=content, isError=data.get("isError", False))


@dataclass
class MCPResourceContent:
    """MCP 资源内容。"""
    uri: str
    text: str
    mimeType: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "MCPResourceContent":
        contents = data.get("contents", [])
        if contents:
            item = contents[0]
            text = item.get("text", "")
            if isinstance(text, bytes):
                text = text.decode("utf-8")
            return cls(
                uri=item.get("uri", ""),
                text=text,
                mimeType=item.get("mimeType"),
            )
        return cls(uri="", text="")
