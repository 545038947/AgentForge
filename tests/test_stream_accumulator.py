"""StreamAccumulator 测试。"""

import pytest
from dataclasses import dataclass

from agentforge.core.stream_accumulator import (
    ToolCallAccumulator,
    StreamAccumulator,
)
from agentforge.types import ToolCall, Usage


@dataclass
class MockToolCallDelta:
    """模拟工具调用增量。"""
    index: int = 0
    id: str = ""
    function: "MockFunction" = None

    def __post_init__(self):
        if self.function is None:
            self.function = MockFunction()


@dataclass
class MockFunction:
    """模拟函数。"""
    name: str = ""
    arguments: str = ""


class TestToolCallAccumulator:
    """测试 ToolCallAccumulator。"""

    def test_add_single_tool_call(self):
        """测试添加单个工具调用。"""
        acc = ToolCallAccumulator()

        # 添加第一个增量（名称）
        delta1 = MockToolCallDelta(index=0, id="call_1", function=MockFunction(name="get_weather"))
        name = acc.add_delta(delta1)
        assert name == "get_weather"

        # 添加第二个增量（参数）
        delta2 = MockToolCallDelta(index=0, function=MockFunction(arguments='{"city": '))
        name = acc.add_delta(delta2)
        assert name is None

        # 添加第三个增量（参数续）
        delta3 = MockToolCallDelta(index=0, function=MockFunction(arguments='"Beijing"}'))
        acc.add_delta(delta3)

        # 获取工具调用
        calls = acc.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].id == "call_1"
        assert calls[0].name == "get_weather"
        assert calls[0].arguments == '{"city": "Beijing"}'

    def test_add_multiple_tool_calls(self):
        """测试添加多个工具调用。"""
        acc = ToolCallAccumulator()

        # 第一个工具
        delta1 = MockToolCallDelta(index=0, id="call_1", function=MockFunction(name="tool_a"))
        name1 = acc.add_delta(delta1)

        # 第二个工具
        delta2 = MockToolCallDelta(index=1, id="call_2", function=MockFunction(name="tool_b"))
        name2 = acc.add_delta(delta2)

        assert name1 == "tool_a"
        assert name2 == "tool_b"

        calls = acc.get_tool_calls()
        assert len(calls) == 2

    def test_ollama_index_reuse(self):
        """测试 Ollama 的 index 重用问题处理。"""
        acc = ToolCallAccumulator()

        # 第一个工具调用，index=0
        delta1 = MockToolCallDelta(index=0, id="call_1", function=MockFunction(name="tool_a"))
        acc.add_delta(delta1)

        # 第二个工具调用，也使用 index=0 但 id 不同
        # Ollama 会重用 index，所以需要检测并分配新 slot
        delta2 = MockToolCallDelta(index=0, id="call_2", function=MockFunction(name="tool_b"))
        acc.add_delta(delta2)

        calls = acc.get_tool_calls()
        # 应该有两个不同的工具调用
        assert len(calls) == 2
        names = {c.name for c in calls}
        assert "tool_a" in names
        assert "tool_b" in names

    def test_function_name_assignment(self):
        """测试函数名使用赋值而非累积。"""
        acc = ToolCallAccumulator()

        # 某些 Provider 可能在每个 chunk 中重复发送 function name
        delta1 = MockToolCallDelta(index=0, id="call_1", function=MockFunction(name="get_weather"))
        acc.add_delta(delta1)

        delta2 = MockToolCallDelta(index=0, function=MockFunction(name="get_weather"))  # 重复发送
        acc.add_delta(delta2)

        calls = acc.get_tool_calls()
        assert calls[0].name == "get_weather"  # 不应该是 "get_weatherget_weather"


class TestStreamAccumulator:
    """测试 StreamAccumulator。"""

    def test_add_content_cumulative(self):
        """测试累积式内容添加。"""
        acc = StreamAccumulator()

        # OpenAI SDK 通常是累积式
        delta1 = acc.add_content("Hello")
        assert delta1 == "Hello"
        assert acc.content == "Hello"

        delta2 = acc.add_content("Hello world")
        assert delta2 == " world"
        assert acc.content == "Hello world"

    def test_add_content_incremental(self):
        """测试增量式内容添加。"""
        acc = StreamAccumulator()

        # 某些 HTTP 直接调用可能是增量式
        delta1 = acc.add_content("Hello")
        assert delta1 == "Hello"

        delta2 = acc.add_content(" world")
        assert delta2 == " world"
        assert acc.content == "Hello world"

    def test_add_reasoning(self):
        """测试推理内容添加。"""
        acc = StreamAccumulator()

        delta1 = acc.add_reasoning("Let me think...")
        assert delta1 == "Let me think..."

        delta2 = acc.add_reasoning("Let me think... First, I need to...")
        assert delta2 == " First, I need to..."

    def test_should_suppress_text_streaming(self):
        """测试工具调用时的文本抑制。"""
        acc = StreamAccumulator()

        # 没有工具调用时不抑制
        assert acc.should_suppress_text_streaming() is False

        # 添加工具调用
        delta = MockToolCallDelta(index=0, id="call_1", function=MockFunction(name="tool"))
        acc.tool_calls.add_delta(delta)

        # 有工具调用时抑制
        assert acc.should_suppress_text_streaming() is True

    def test_build_response_text_only(self):
        """测试构建纯文本响应。"""
        acc = StreamAccumulator()
        acc.add_content("Hello world")
        acc.update_usage(Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15))

        response = acc.build_response()
        assert response.content == "Hello world"
        assert response.tool_calls is None
        assert response.finish_reason == "stop"
        assert response.usage.total_tokens == 15

    def test_build_response_with_tool_calls(self):
        """测试构建工具调用响应。"""
        acc = StreamAccumulator()
        acc.add_content("I will use a tool.")

        delta = MockToolCallDelta(index=0, id="call_1", function=MockFunction(name="get_weather", arguments='{"city": "Beijing"}'))
        acc.tool_calls.add_delta(delta)

        response = acc.build_response()
        assert response.content == "I will use a tool."
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.finish_reason == "tool_calls"

    def test_update_model(self):
        """测试更新模型名称。"""
        acc = StreamAccumulator()
        acc.update_model("gpt-4o")

        assert acc.model == "gpt-4o"

    def test_has_methods(self):
        """测试 has 方法。"""
        acc = StreamAccumulator()

        assert acc.has_content() is False
        assert acc.has_reasoning() is False
        assert acc.has_tool_calls() is False

        acc.add_content("test")
        assert acc.has_content() is True

        acc.add_reasoning("thinking")
        assert acc.has_reasoning() is True

        delta = MockToolCallDelta(index=0, function=MockFunction(name="tool"))
        acc.tool_calls.add_delta(delta)
        assert acc.has_tool_calls() is True
