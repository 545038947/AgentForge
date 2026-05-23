"""消息类型定义。

定义 Agent 对话中的消息结构，支持多模态内容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union


@dataclass
class TextContent:
    """文本内容块。"""
    type: str = field(default="text", init=False)
    text: str


@dataclass
class ImageContent:
    """图片内容块。

    支持两种格式：
    - url: 图片 URL
    - base64: Base64 编码的图片数据
    """
    type: str = field(default="image", init=False)
    url: Optional[str] = None
    base64: Optional[str] = None
    media_type: Optional[str] = None  # 如 "image/png", "image/jpeg"

    def __post_init__(self):
        if not self.url and not self.base64:
            raise ValueError("ImageContent 必须提供 url 或 base64")


@dataclass
class ToolUseContent:
    """工具调用内容块。

    表示 Agent 发起的工具调用请求。
    """
    type: str = field(default="tool_use", init=False)
    id: str  # 工具调用唯一标识
    name: str  # 工具名称
    input: dict  # 工具参数


@dataclass
class ToolResultContent:
    """工具结果内容块。

    表示工具执行的返回结果。
    """
    type: str = field(default="tool_result", init=False)
    tool_use_id: str  # 对应的 ToolUseContent.id
    content: str  # 工具返回内容
    is_error: bool = False  # 是否为错误结果


# 内容块联合类型
ContentBlock = Union[TextContent, ImageContent, ToolUseContent, ToolResultContent]


@dataclass
class Message:
    """对话消息。

    支持两种内容格式：
    - 纯文本: content 为字符串
    - 多模态: content 为 ContentBlock 列表
    """
    role: str  # "system" | "user" | "assistant"
    content: Union[str, List[ContentBlock]]
    name: Optional[str] = None  # 消息发送者名称（可选）

    def __post_init__(self):
        # 验证 role
        valid_roles = ("system", "user", "assistant")
        if self.role not in valid_roles:
            raise ValueError(f"Message.role 必须是 {valid_roles} 之一，当前为 {self.role}")

    @property
    def is_text_only(self) -> bool:
        """检查是否为纯文本消息。"""
        return isinstance(self.content, str)

    @property
    def text_content(self) -> Optional[str]:
        """获取文本内容（如果是纯文本或包含文本块）。"""
        if isinstance(self.content, str):
            return self.content

        # 从多模态内容中提取文本
        for block in self.content:
            if isinstance(block, TextContent):
                return block.text
        return None

    def to_dict(self) -> dict:
        """转换为字典格式（用于 API 调用）。"""
        if isinstance(self.content, str):
            content_dict = self.content
        else:
            content_dict = []
            for block in self.content:
                if isinstance(block, TextContent):
                    content_dict.append({"type": "text", "text": block.text})
                elif isinstance(block, ImageContent):
                    if block.url:
                        content_dict.append({
                            "type": "image_url",
                            "image_url": {"url": block.url}
                        })
                    elif block.base64:
                        content_dict.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{block.media_type or 'image/png'};base64,{block.base64}"
                            }
                        })
                elif isinstance(block, ToolUseContent):
                    content_dict.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })
                elif isinstance(block, ToolResultContent):
                    content_dict.append({
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": block.is_error
                    })

        result = {"role": self.role, "content": content_dict}
        if self.name:
            result["name"] = self.name
        return result