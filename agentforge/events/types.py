"""事件类型定义。

定义 Agent 运行过程中的事件类型。
"""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass
from typing import Any, Dict, Optional


class EventType(enum.Enum):
    """事件类型枚举。

    定义 Agent 运行过程中的所有事件类型。
    """

    # Agent 生命周期
    AGENT_START = "agent.start"
    AGENT_END = "agent.end"
    AGENT_INTERRUPT = "agent.interrupt"
    AGENT_THINKING = "agent.thinking"       # 思考过程（流式）
    AGENT_REASONING = "agent.reasoning"     # 推理过程（流式）
    AGENT_STATUS = "agent.status"           # 状态更新

    # 工具执行
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    TOOL_ERROR = "tool.error"
    TOOL_PROGRESS = "tool.progress"         # 工具执行进度
    TOOL_APPROVAL_REQUIRED = "tool.approval_required"
    TOOL_GENERATED = "tool.generated"       # 工具调用生成

    # Provider 调用
    PROVIDER_REQUEST = "provider.request"
    PROVIDER_RESPONSE = "provider.response"
    PROVIDER_ERROR = "provider.error"
    STREAM_DELTA = "stream.delta"           # 流式 Token 增量
    STREAM_CHUNK = "stream.chunk"           # 流式响应块
    STREAM_END = "stream.end"               # 流式结束

    # 上下文压缩
    COMPRESSION_START = "compression.start"
    COMPRESSION_END = "compression.end"

    # 委托
    DELEGATION_START = "delegation.start"
    DELEGATION_END = "delegation.end"

    # 用户交互
    CLARIFY_REQUEST = "clarify.request"     # 澄清请求
    INTERIM_ASSISTANT = "interim.assistant" # 中间 assistant 消息

    # 记忆系统
    MEMORY_PREFETCH = "memory.prefetch"
    MEMORY_PREFETCH_DONE = "memory.prefetch_done"
    MEMORY_SYNC = "memory.sync"
    MEMORY_SYNC_DONE = "memory.sync_done"


@dataclass
class Event:
    """事件数据类。

    封装事件的完整信息，支持追踪和过滤。

    属性：
        id: 事件唯一标识
        type: 事件类型
        timestamp: Unix 时间戳
        trace_id: 追踪 ID（用于关联相关事件）
        span_id: 当前 span ID
        parent_span_id: 父 span ID（可选）
        data: 事件数据
    """

    id: str
    type: EventType
    timestamp: float
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "data": self.data,
        }
