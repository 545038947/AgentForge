"""事件发射器。

提供事件分发和监听器管理功能。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agentforge.events.types import Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class EventListener:
    """事件监听器。

    属性：
        callback: 回调函数
        priority: 优先级（数值越小优先级越高）
        filter_func: 过滤函数（可选）
    """
    callback: Callable[[Event], None]
    priority: int = 0
    filter_func: Optional[Callable[[Event], bool]] = None


class EventEmitter:
    """事件发射器，负责事件分发。

    功能：
    - 注册/移除事件监听器
    - 支持优先级排序
    - 支持过滤函数
    - 线程安全

    使用示例：
        emitter = EventEmitter()

        # 注册监听器
        emitter.on(EventType.TOOL_START, lambda e: print(f"Tool: {e.data['name']}"))

        # 发射事件
        emitter.emit(Event(type=EventType.TOOL_START, data={"name": "search"}))
    """

    def __init__(self):
        self._listeners: Dict[EventType, List[EventListener]] = {}
        self._lock = threading.Lock()
        self._trace_id: str = str(uuid.uuid4())
        self._span_counter: int = 0

    def on(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
        priority: int = 0,
        filter_func: Optional[Callable[[Event], bool]] = None,
    ) -> None:
        """注册事件监听器。

        Args:
            event_type: 事件类型
            callback: 回调函数
            priority: 优先级（数值越小优先级越高）
            filter_func: 过滤函数，返回 True 时才触发回调
        """
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            listener = EventListener(
                callback=callback,
                priority=priority,
                filter_func=filter_func,
            )
            self._listeners[event_type].append(listener)
            # 按优先级排序
            self._listeners[event_type].sort(key=lambda l: l.priority)

    def off(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
    ) -> bool:
        """移除事件监听器。

        Args:
            event_type: 事件类型
            callback: 要移除的回调函数

        Returns:
            True 如果成功移除，False 如果未找到
        """
        with self._lock:
            if event_type not in self._listeners:
                return False
            for i, listener in enumerate(self._listeners[event_type]):
                if listener.callback == callback:
                    self._listeners[event_type].pop(i)
                    return True
            return False

    def emit(self, event: Event) -> None:
        """发射事件，触发所有匹配的监听器。

        Args:
            event: 事件对象
        """
        with self._lock:
            listeners = self._listeners.get(event.type, [])

        for listener in listeners:
            # 检查过滤函数
            if listener.filter_func:
                try:
                    if not listener.filter_func(event):
                        continue
                except Exception as e:
                    logger.warning(f"Event filter error: {e}")
                    continue

            # 调用回调
            try:
                listener.callback(event)
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

    def create_event(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        parent_span_id: Optional[str] = None,
    ) -> Event:
        """创建事件对象。

        自动生成 id、timestamp、trace_id、span_id。

        Args:
            event_type: 事件类型
            data: 事件数据
            parent_span_id: 父 span ID

        Returns:
            新创建的 Event 对象
        """
        with self._lock:
            self._span_counter += 1
            span_id = f"{self._trace_id}-{self._span_counter}"

        return Event(
            id=str(uuid.uuid4()),
            type=event_type,
            timestamp=time.time(),
            trace_id=self._trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            data=data,
        )

    def emit_event(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        parent_span_id: Optional[str] = None,
    ) -> Event:
        """创建并发射事件。

        Args:
            event_type: 事件类型
            data: 事件数据
            parent_span_id: 父 span ID

        Returns:
            发射的事件对象
        """
        event = self.create_event(event_type, data, parent_span_id)
        self.emit(event)
        return event

    def clear(self) -> None:
        """清空所有监听器。"""
        with self._lock:
            self._listeners.clear()

    def set_trace_id(self, trace_id: str) -> None:
        """设置追踪 ID。

        Args:
            trace_id: 新的追踪 ID
        """
        with self._lock:
            self._trace_id = trace_id
            self._span_counter = 0


class EventDispatcher(EventEmitter):
    """事件分发器，作为 Agent 的中央事件管理器。

    继承 EventEmitter，提供额外的便捷方法。
    """

    def __init__(self):
        super().__init__()

    def dispatch(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """分发事件。

        Args:
            event_type: 事件类型
            data: 事件数据

        Returns:
            分发的事件对象
        """
        return self.emit_event(event_type, data)

    def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
        priority: int = 0,
    ) -> None:
        """订阅事件。

        Args:
            event_type: 事件类型
            callback: 回调函数
            priority: 优先级
        """
        self.on(event_type, callback, priority)