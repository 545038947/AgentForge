"""流式响应测试。"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Iterator, List

from hai_agent import Agent, StreamDelta, EventType
from hai_agent.types import NormalizedResponse, ToolCall, Usage
from hai_agent.providers.builtins import OpenAIProvider


class TestStreamDelta:
    """测试 StreamDelta 类型。"""

    def test_create_basic_delta(self):
        """测试基本增量创建。"""
        delta = StreamDelta(content="你好")
        assert delta.content == "你好"
        assert delta.has_content is True
        assert delta.has_reasoning is False
        assert delta.is_final is False

    def test_create_reasoning_delta(self):
        """测试推理增量。"""
        delta = StreamDelta(reasoning="思考中...")
        assert delta.reasoning == "思考中..."
        assert delta.has_reasoning is True
        assert delta.has_content is False

    def test_create_final_delta(self):
        """测试最终增量。"""
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        delta = StreamDelta(
            content="",
            finish_reason="stop",
            usage=usage,
        )
        assert delta.is_final is True
        assert delta.finish_reason == "stop"
        assert delta.usage is not None
        assert delta.usage.prompt_tokens == 100

    def test_create_tool_call_delta(self):
        """测试工具调用增量。"""
        tool_call = ToolCall(id="tc_1", name="search", arguments='{"query": "test"}')
        delta = StreamDelta(tool_calls=[tool_call])
        assert delta.has_tool_calls is True
        assert len(delta.tool_calls) == 1

    def test_empty_delta(self):
        """测试空增量。"""
        delta = StreamDelta()
        assert delta.has_content is False
        assert delta.has_reasoning is False
        assert delta.has_tool_calls is False
        assert delta.is_final is False

    def test_repr(self):
        """测试字符串表示。"""
        delta = StreamDelta(content="测试")
        assert "content=" in repr(delta)
        assert "测试" in repr(delta)


class TestStreamDeltas:
    """测试 Agent.stream_deltas 方法。"""

    def _create_mock_provider(self, response_chunks: List[NormalizedResponse]):
        """创建模拟 Provider。"""
        mock_provider = MagicMock(spec=OpenAIProvider)
        mock_provider.capabilities.supports_tools = True
        mock_provider.capabilities.supports_streaming = True

        def mock_stream(messages, tools=None, **kwargs):
            for chunk in response_chunks:
                yield chunk

        mock_provider.stream = mock_stream
        return mock_provider

    def test_stream_deltas_basic(self):
        """测试基本流式增量。"""
        # 创建模拟响应序列（模拟增量）
        responses = [
            NormalizedResponse(content="你"),
            NormalizedResponse(content="你好"),
            NormalizedResponse(content="你好！"),
            NormalizedResponse(
                content="你好！有什么可以帮助你的吗？",
                finish_reason="stop",
                usage=Usage(prompt_tokens=10, completion_tokens=20),
            ),
        ]

        mock_provider = self._create_mock_provider(responses)

        with patch.object(Agent, "_auto_select_provider", return_value=mock_provider):
            agent = Agent.__new__(Agent)
            agent._provider = mock_provider
            agent._tools = {}
            agent._message_manager = MagicMock()
            agent._event_dispatcher = MagicMock()
            agent._interrupt_handler = MagicMock()
            agent._iteration_budget = MagicMock()
            agent._iteration_budget.remaining = 10
            agent._iteration_budget.consume = MagicMock()
            agent._guardrails = MagicMock()
            agent._execution_engine = MagicMock()

            # 模拟中断检查
            interrupt_token = MagicMock()
            interrupt_token.check.return_value = False
            agent._interrupt_handler.create_token.return_value = interrupt_token

            # 收集增量
            deltas = list(agent.stream_deltas("你好"))

            # 验证增量数量
            assert len(deltas) >= 3  # 至少有内容增量

            # 验证内容增量
            content_parts = [d.content for d in deltas if d.has_content]
            # 增量应该是 "你" -> "好" -> "！" -> "有什么可以帮助你的吗？"
            assert len(content_parts) >= 3

            # 验证最终增量
            final_deltas = [d for d in deltas if d.is_final]
            assert len(final_deltas) >= 1

    def test_stream_deltas_with_tool_calls(self):
        """测试带工具调用的流式增量。"""
        tool_call = ToolCall(id="tc_1", name="search", arguments='{"query": "test"}')
        responses = [
            NormalizedResponse(content="让我"),
            NormalizedResponse(content="让我搜索"),
            NormalizedResponse(
                content="让我搜索一下",
                tool_calls=[tool_call],
                finish_reason="tool_calls",
            ),
        ]

        mock_provider = self._create_mock_provider(responses)

        with patch.object(Agent, "_auto_select_provider", return_value=mock_provider):
            agent = Agent.__new__(Agent)
            agent._provider = mock_provider
            agent._tools = {"search": MagicMock()}
            agent._message_manager = MagicMock()
            agent._event_dispatcher = MagicMock()
            agent._interrupt_handler = MagicMock()
            agent._iteration_budget = MagicMock()
            agent._iteration_budget.remaining = 10
            agent._iteration_budget.consume = MagicMock()
            agent._guardrails = MagicMock()

            # 模拟工具执行
            mock_result = MagicMock()
            mock_result.is_error = False
            mock_result.tool_name = "search"
            agent._execution_engine = MagicMock()
            agent._execution_engine.execute_tool_calls.return_value = [mock_result]

            interrupt_token = MagicMock()
            interrupt_token.check.return_value = False
            agent._interrupt_handler.create_token.return_value = interrupt_token

            deltas = list(agent.stream_deltas("搜索 test"))

            # 应包含工具执行提示
            tool_deltas = [d for d in deltas if "执行工具" in d.content]
            assert len(tool_deltas) >= 1

    def test_stream_deltas_interrupt(self):
        """测试中断流式响应。"""
        responses = [
            NormalizedResponse(content="正在"),
            NormalizedResponse(content="正在处理"),
            NormalizedResponse(
                content="正在处理...",
                finish_reason="stop",
            ),
        ]

        mock_provider = self._create_mock_provider(responses)

        with patch.object(Agent, "_auto_select_provider", return_value=mock_provider):
            agent = Agent.__new__(Agent)
            agent._provider = mock_provider
            agent._tools = {}
            agent._message_manager = MagicMock()
            agent._event_dispatcher = MagicMock()
            agent._interrupt_handler = MagicMock()
            agent._iteration_budget = MagicMock()
            agent._iteration_budget.remaining = 10
            agent._iteration_budget.consume = MagicMock()
            agent._guardrails = MagicMock()
            agent._execution_engine = MagicMock()

            interrupt_token = MagicMock()
            # 模拟在第一轮完成后中断
            interrupt_token.check.side_effect = [False, True]  # 开始时 False，第二轮检查时 True
            interrupt_token.reason = "用户中断"
            agent._interrupt_handler.create_token.return_value = interrupt_token

            deltas = list(agent.stream_deltas("你好"))

            # 验证收集到增量
            assert len(deltas) >= 1
            # 由于中断发生在第二轮检查，第一轮的增量应该已收集


class TestStreamExports:
    """测试流式类型导出。"""

    def test_stream_delta_exported(self):
        """测试 StreamDelta 从主模块导出。"""
        from hai_agent import StreamDelta as SD
        delta = SD(content="test")
        assert delta.content == "test"

    def test_stream_delta_in_all(self):
        """测试 __all__ 包含 StreamDelta。"""
        import hai_agent
        assert "StreamDelta" in hai_agent.__all__