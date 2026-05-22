"""事件系统模块。"""

from typing import Callable

from agentforge.events.types import EventType, Event
from agentforge.events.emitter import EventEmitter, EventDispatcher, EventListener


def on_event(event_type: EventType) -> Callable[[Callable], Callable]:
    """事件监听装饰器。

    简化事件监听器的注册，返回的装饰器会标记函数为事件处理器。
    实际注册需要在 Agent 上调用 agent.on()。

    Args:
        event_type: 事件类型

    Returns:
        装饰器函数

    使用示例：
        from agentforge.events import on_event, EventType

        @on_event(EventType.TOOL_START)
        def handle_tool_start(event):
            print(f"工具开始: {event.data}")

        # 在 Agent 上注册
        agent.on(EventType.TOOL_START, handle_tool_start)
    """
    def decorator(func: Callable) -> Callable:
        func._agentforge_event_type = event_type
        return func
    return decorator


__all__ = [
    "EventType",
    "Event",
    "EventEmitter",
    "EventDispatcher",
    "EventListener",
    "on_event",
]