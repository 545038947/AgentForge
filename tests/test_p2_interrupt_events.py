"""P2 阶段单元测试：中断与事件系统。"""

import pytest
import threading
import time

from agentforge.interrupt import InterruptToken, InterruptHandler
from agentforge.events import EventType, Event, EventEmitter, EventDispatcher


class TestInterruptToken:
    """InterruptToken 测试。"""

    def test_create_token(self):
        """测试创建令牌。"""
        token = InterruptToken()
        assert not token.is_interrupted
        assert token.reason is None

    def test_interrupt(self):
        """测试中断请求。"""
        token = InterruptToken()
        token.interrupt("用户取消")
        assert token.is_interrupted
        assert token.reason == "用户取消"

    def test_reset(self):
        """测试重置。"""
        token = InterruptToken()
        token.interrupt("测试")
        assert token.is_interrupted

        token.reset()
        assert not token.is_interrupted
        assert token.reason is None

    def test_create_child(self):
        """测试创建子令牌。"""
        parent = InterruptToken()
        child = parent.create_child()

        assert not child.is_interrupted
        assert child._parent is parent

    def test_child_inherits_interrupt(self):
        """测试子令牌继承中断状态。"""
        parent = InterruptToken()
        child = parent.create_child()

        parent.interrupt("父中断")

        # 子令牌检查应该返回 True
        assert child.check()
        # 但子令牌自身的 is_interrupted 是 False
        assert not child.is_interrupted

    def test_child_own_interrupt(self):
        """测试子令牌自身中断。"""
        parent = InterruptToken()
        child = parent.create_child()

        child.interrupt("子中断")

        assert child.is_interrupted
        assert child.check()
        # 父令牌不受影响
        assert not parent.is_interrupted

    def test_thread_safety(self):
        """测试线程安全。"""
        token = InterruptToken()
        results = []

        def interrupt_loop():
            for _ in range(100):
                token.interrupt("测试")
                results.append(token.is_interrupted)
                token.reset()

        threads = [threading.Thread(target=interrupt_loop) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有操作都应该成功完成
        assert len(results) == 1000


class TestInterruptHandler:
    """InterruptHandler 测试。"""

    def test_create_token(self):
        """测试创建令牌。"""
        handler = InterruptHandler()
        token = handler.create_token()

        assert token is not None
        assert not token.is_interrupted

    def test_create_child_token(self):
        """测试创建子令牌。"""
        handler = InterruptHandler()
        handler.create_token()  # 先创建主令牌

        child = handler.create_child_token()
        assert child._parent is handler._main_token

    def test_propagate_interrupt(self):
        """测试传播中断。"""
        handler = InterruptHandler()
        handler.create_token()
        child1 = handler.create_child_token()
        child2 = handler.create_child_token()

        handler.propagate_interrupt("测试中断")

        assert handler._main_token.is_interrupted
        assert child1.is_interrupted
        assert child2.is_interrupted

    def test_register_unregister_child(self):
        """测试注册和取消注册子令牌。"""
        handler = InterruptHandler()
        handler.create_token()

        child = InterruptToken()
        handler.register_child(child)
        assert child in handler._child_tokens

        handler.unregister_child(child)
        assert child not in handler._child_tokens

    def test_is_interrupted(self):
        """测试中断状态检查。"""
        handler = InterruptHandler()
        handler.create_token()

        assert not handler.is_interrupted()

        handler.propagate_interrupt()
        assert handler.is_interrupted()

    def test_reset(self):
        """测试重置。"""
        handler = InterruptHandler()
        handler.create_token()
        handler.propagate_interrupt()

        handler.reset()
        assert not handler.is_interrupted()

    def test_clear(self):
        """测试清空。"""
        handler = InterruptHandler()
        handler.create_token()
        handler.create_child_token()

        handler.clear()
        assert handler._main_token is None
        assert len(handler._child_tokens) == 0


class TestEventType:
    """EventType 测试。"""

    def test_event_types(self):
        """测试事件类型值。"""
        assert EventType.AGENT_START.value == "agent.start"
        assert EventType.TOOL_START.value == "tool.start"
        assert EventType.PROVIDER_REQUEST.value == "provider.request"

    def test_event_type_count(self):
        """测试事件类型数量。"""
        # 确保有足够的事件类型
        assert len(EventType) >= 10


class TestEvent:
    """Event 测试。"""

    def test_create_event(self):
        """测试创建事件。"""
        event = Event(
            id="test-1",
            type=EventType.TOOL_START,
            timestamp=time.time(),
            trace_id="trace-1",
            span_id="span-1",
            data={"name": "search"},
        )

        assert event.id == "test-1"
        assert event.type == EventType.TOOL_START
        assert event.data == {"name": "search"}

    def test_event_to_dict(self):
        """测试事件转字典。"""
        event = Event(
            id="test-1",
            type=EventType.TOOL_START,
            timestamp=12345.0,
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id="parent-1",
            data={"name": "search"},
        )

        d = event.to_dict()
        assert d["id"] == "test-1"
        assert d["type"] == "tool.start"
        assert d["timestamp"] == 12345.0
        assert d["parent_span_id"] == "parent-1"


class TestEventEmitter:
    """EventEmitter 测试。"""

    def test_on_and_emit(self):
        """测试注册监听器和发射事件。"""
        emitter = EventEmitter()
        received = []

        def callback(event):
            received.append(event)

        emitter.on(EventType.TOOL_START, callback)
        event = emitter.create_event(EventType.TOOL_START, {"name": "search"})
        emitter.emit(event)

        assert len(received) == 1
        assert received[0].data == {"name": "search"}

    def test_priority(self):
        """测试优先级排序。"""
        emitter = EventEmitter()
        order = []

        def callback_low(event):
            order.append("low")

        def callback_high(event):
            order.append("high")

        emitter.on(EventType.TOOL_START, callback_low, priority=10)
        emitter.on(EventType.TOOL_START, callback_high, priority=0)

        event = emitter.create_event(EventType.TOOL_START)
        emitter.emit(event)

        assert order == ["high", "low"]

    def test_filter(self):
        """测试过滤函数。"""
        emitter = EventEmitter()
        received = []

        def callback(event):
            received.append(event)

        def filter_func(event):
            return event.data and event.data.get("important", False)

        emitter.on(EventType.TOOL_START, callback, filter_func=filter_func)

        # 不匹配过滤条件
        emitter.emit_event(EventType.TOOL_START, {"important": False})
        assert len(received) == 0

        # 匹配过滤条件
        emitter.emit_event(EventType.TOOL_START, {"important": True})
        assert len(received) == 1

    def test_off(self):
        """测试移除监听器。"""
        emitter = EventEmitter()
        received = []

        def callback(event):
            received.append(event)

        emitter.on(EventType.TOOL_START, callback)
        emitter.emit_event(EventType.TOOL_START)
        assert len(received) == 1

        # 移除监听器
        result = emitter.off(EventType.TOOL_START, callback)
        assert result is True

        emitter.emit_event(EventType.TOOL_START)
        assert len(received) == 1  # 没有增加

    def test_off_not_found(self):
        """测试移除不存在的监听器。"""
        emitter = EventEmitter()

        def callback(event):
            pass

        result = emitter.off(EventType.TOOL_START, callback)
        assert result is False

    def test_create_event(self):
        """测试创建事件。"""
        emitter = EventEmitter()

        event = emitter.create_event(EventType.TOOL_START, {"name": "test"})

        assert event.type == EventType.TOOL_START
        assert event.data == {"name": "test"}
        assert event.trace_id == emitter._trace_id
        assert event.span_id is not None

    def test_emit_event(self):
        """测试创建并发射事件。"""
        emitter = EventEmitter()
        received = []

        emitter.on(EventType.TOOL_START, lambda e: received.append(e))

        event = emitter.emit_event(EventType.TOOL_START, {"name": "test"})

        assert len(received) == 1
        assert received[0] is event

    def test_clear(self):
        """测试清空监听器。"""
        emitter = EventEmitter()
        received = []

        emitter.on(EventType.TOOL_START, lambda e: received.append(e))
        emitter.clear()

        emitter.emit_event(EventType.TOOL_START)
        assert len(received) == 0

    def test_set_trace_id(self):
        """测试设置追踪 ID。"""
        emitter = EventEmitter()

        emitter.set_trace_id("new-trace")
        assert emitter._trace_id == "new-trace"

        event = emitter.create_event(EventType.TOOL_START)
        assert event.trace_id == "new-trace"


class TestEventDispatcher:
    """EventDispatcher 测试。"""

    def test_dispatch(self):
        """测试分发事件。"""
        dispatcher = EventDispatcher()
        received = []

        dispatcher.subscribe(EventType.TOOL_START, lambda e: received.append(e))

        event = dispatcher.dispatch(EventType.TOOL_START, {"name": "test"})

        assert len(received) == 1
        assert received[0] is event

    def test_subscribe(self):
        """测试订阅事件。"""
        dispatcher = EventDispatcher()
        received = []

        dispatcher.subscribe(EventType.TOOL_START, lambda e: received.append(e))
        dispatcher.dispatch(EventType.TOOL_START)

        assert len(received) == 1
