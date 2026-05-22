"""便捷函数测试。"""

import pytest
from unittest.mock import patch, MagicMock

from agentforge import quick_chat, on_event, Agent, EventType


class TestQuickChat:
    """测试 quick_chat 便捷函数。"""

    def test_quick_chat_basic(self):
        """测试基本单次对话。"""
        with patch.object(Agent, "_auto_select_provider") as mock_select:
            with patch.object(Agent, "run") as mock_run:
                # 设置 mock
                mock_response = MagicMock()
                mock_response.content = "你好！有什么可以帮助你的吗？"
                mock_run.return_value = mock_response
                mock_select.return_value = MagicMock()

                # 调用 quick_chat
                result = quick_chat("你好", model="gpt-4")

                # 验证
                assert result == "你好！有什么可以帮助你的吗？"
                mock_run.assert_called_once()

    def test_quick_chat_with_api_key(self):
        """测试带 API Key 的单次对话。"""
        with patch.object(Agent, "_auto_select_provider") as mock_select:
            with patch.object(Agent, "run") as mock_run:
                mock_response = MagicMock()
                mock_response.content = "响应内容"
                mock_run.return_value = mock_response
                mock_select.return_value = MagicMock()

                result = quick_chat("测试消息", model="gpt-4", api_key="test-key")

                assert result == "响应内容"
                # 验证 API Key 传递到 auto_select
                mock_select.assert_called_once()
                call_args = mock_select.call_args[0]
                assert call_args[0] == "gpt-4"
                assert call_args[1] == "test-key"

    def test_quick_chat_empty_response(self):
        """测试空响应情况。"""
        with patch.object(Agent, "_auto_select_provider") as mock_select:
            with patch.object(Agent, "run") as mock_run:
                mock_response = MagicMock()
                mock_response.content = None
                mock_run.return_value = mock_response
                mock_select.return_value = MagicMock()

                result = quick_chat("测试")

                assert result == ""


class TestOnEvent:
    """测试 on_event 事件监听装饰器。"""

    def test_on_event_marks_function(self):
        """测试装饰器标记函数。"""
        @on_event(EventType.TOOL_START)
        def handle_tool_start(event):
            return event

        # 验证函数被标记
        assert hasattr(handle_tool_start, "_agentforge_event_type")
        assert handle_tool_start._agentforge_event_type == EventType.TOOL_START

    def test_on_event_preserves_function(self):
        """测试装饰器保留原函数。"""
        @on_event(EventType.AGENT_THINKING)
        def original_function(event):
            """原始函数文档。"""
            return "result"

        # 验证函数行为不变
        assert original_function({}) == "result"
        assert original_function.__doc__ == "原始函数文档。"

    def test_on_event_different_types(self):
        """测试不同事件类型的装饰器。"""
        @on_event(EventType.STREAM_DELTA)
        def handle_stream(event):
            pass

        @on_event(EventType.TOOL_PROGRESS)
        def handle_progress(event):
            pass

        assert handle_stream._agentforge_event_type == EventType.STREAM_DELTA
        assert handle_progress._agentforge_event_type == EventType.TOOL_PROGRESS

    def test_on_event_with_agent_registration(self):
        """测试装饰器函数可注册到 Agent。"""
        @on_event(EventType.TOOL_START)
        def handler(event):
            pass

        # 创建 Agent 并注册
        with patch("agentforge.Agent._auto_select_provider"):
            agent = MagicMock(spec=Agent)
            agent.on = MagicMock()

            # 模拟注册过程
            agent.on(EventType.TOOL_START, handler)

            # 验证注册调用
            agent.on.assert_called_once_with(EventType.TOOL_START, handler)


class TestConvenienceExports:
    """测试便捷函数导出。"""

    def test_quick_chat_exported(self):
        """测试 quick_chat 从主模块导出。"""
        from agentforge import quick_chat as qc
        assert callable(qc)

    def test_on_event_exported(self):
        """测试 on_event 从主模块导出。"""
        from agentforge import on_event as oe
        assert callable(oe)

    def test_all_includes_convenience_functions(self):
        """测试 __all__ 包含便捷函数。"""
        import agentforge
        assert "quick_chat" in agentforge.__all__
        assert "on_event" in agentforge.__all__
