"""会话信息数据结构。"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionInfo:
    """会话信息。

    Attributes:
        id: 会话 ID
        source: 来源（cli、telegram、discord 等）
        user_id: 用户 ID
        model: 模型名称
        model_config: 模型配置
        system_prompt: 系统提示
        parent_session_id: 父会话 ID（压缩链/分支链）
        started_at: 开始时间戳
        ended_at: 结束时间戳
        end_reason: 结束原因
        message_count: 消息数量
        title: 会话标题
    """

    id: str
    source: str
    user_id: Optional[str] = None
    model: Optional[str] = None
    model_config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    parent_session_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    end_reason: Optional[str] = None
    message_count: int = 0
    title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionInfo":
        """从字典创建。"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MessageRecord:
    """消息记录。

    Attributes:
        id: 消息 ID
        session_id: 会话 ID
        role: 角色（user、assistant）
        content: 消息内容（str 或 List[ContentBlock]）
        tool_call_id: 工具调用 ID
        tool_calls: 工具调用列表
        tool_name: 工具名称
        timestamp: 时间戳
        token_count: Token 数量
        finish_reason: 结束原因
        reasoning: 推理内容
    """

    id: int
    session_id: str
    role: str
    content: Any
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_name: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    token_count: Optional[int] = None
    finish_reason: Optional[str] = None
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageRecord":
        """从字典创建。"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})