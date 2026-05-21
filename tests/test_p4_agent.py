"""P4 阶段单元测试：Agent 核心与上下文压缩。"""

import pytest
import time

from agentforge.managers import MessageManager, ToolOrchestrator
from agentforge.context import TokenEstimator, ContextCompressor
from agentforge.types import (
    Message,
    TextContent,
    ToolUseContent,
    ToolResultContent,
    ToolResult,
    NormalizedResponse,
    ToolCall,
)
from agentforge.config import Settings


# ── 测试辅助类 ──────────────────────────────────────────────

class MockProvider:
    """模拟 Provider。"""

    def __init__(self, responses=None):
        self._responses = responses or []
        self._call_count = 0

    def complete(self, messages, tools=None, **kwargs):
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
            self._call_count += 1
            return response
        return NormalizedResponse(content="默认响应")

    def stream(self, messages, tools=None, **kwargs):
        response = self.complete(messages, tools, **kwargs)
        yield response


def create_settings():
    """创建测试用的 Settings。"""
    return Settings(model="test-model")


# ── MessageManager 测试 ──────────────────────────────────────────────

class TestMessageManager:
    """MessageManager 测试。"""

    def test_create_manager(self):
        """测试创建管理器。"""
        settings = create_settings()
        manager = MessageManager(settings)

        assert len(manager) == 0

    def test_add_user_message(self):
        """测试添加用户消息。"""
        settings = create_settings()
        manager = MessageManager(settings)

        manager.add_user_message("你好")

        assert len(manager) == 1
        messages = manager.get_messages()
        assert messages[0].role == "user"

    def test_add_assistant_message(self):
        """测试添加 assistant 消息。"""
        settings = create_settings()
        manager = MessageManager(settings)

        response = NormalizedResponse(content="你好！")
        manager.add_assistant_message(response)

        assert len(manager) == 1
        messages = manager.get_messages()
        assert messages[0].role == "assistant"

    def test_add_tool_results(self):
        """测试添加工具结果。"""
        settings = create_settings()
        manager = MessageManager(settings)

        results = [
            ToolResult(tool_call_id="call-1", content="结果1"),
            ToolResult(tool_call_id="call-2", content="结果2"),
        ]
        manager.add_tool_results(results)

        assert len(manager) == 2

    def test_get_context(self):
        """测试获取上下文。"""
        settings = create_settings()
        manager = MessageManager(settings)

        manager.add_user_message("问题1")
        manager.add_user_message("问题2")

        context = manager.get_context()
        assert len(context) == 2

    def test_clear(self):
        """测试清空消息。"""
        settings = create_settings()
        manager = MessageManager(settings)

        manager.add_user_message("测试")
        manager.clear()

        assert len(manager) == 0

    def test_iterate_messages(self):
        """测试迭代消息。"""
        settings = create_settings()
        manager = MessageManager(settings)

        manager.add_user_message("消息1")
        manager.add_user_message("消息2")

        count = 0
        for msg in manager:
            count += 1

        assert count == 2


# ── ToolOrchestrator 测试 ──────────────────────────────────────────────

class TestToolOrchestrator:
    """ToolOrchestrator 测试。"""

    def test_create_orchestrator(self):
        """测试创建编排器。"""
        settings = create_settings()
        orchestrator = ToolOrchestrator(settings)

        assert orchestrator is not None

    def test_execute_empty_calls(self):
        """测试执行空调用列表。"""
        settings = create_settings()
        orchestrator = ToolOrchestrator(settings)

        results = orchestrator.execute([], {})
        assert results == []

    def test_execute_tool_not_found(self):
        """测试工具不存在。"""
        settings = create_settings()
        orchestrator = ToolOrchestrator(settings)

        tool_calls = [ToolCall(id="call-1", name="unknown", arguments="{}")]
        results = orchestrator.execute(tool_calls, {})

        assert len(results) == 1
        assert results[0].is_error
        assert "未找到工具" in results[0].content

    def test_shutdown(self):
        """测试关闭编排器。"""
        settings = create_settings()
        orchestrator = ToolOrchestrator(settings)

        # 执行一次以初始化执行器
        orchestrator.execute([], {})

        orchestrator.shutdown()
        assert orchestrator._executor is None


# ── TokenEstimator 测试 ──────────────────────────────────────────────

class TestTokenEstimator:
    """TokenEstimator 测试。"""

    def test_estimate_text_empty(self):
        """测试空文本估算。"""
        estimator = TokenEstimator()
        assert estimator.estimate_text("") == 0

    def test_estimate_text_english(self):
        """测试英文文本估算。"""
        estimator = TokenEstimator()
        tokens = estimator.estimate_text("Hello World")
        assert tokens > 0

    def test_estimate_text_chinese(self):
        """测试中文文本估算。"""
        estimator = TokenEstimator()
        tokens = estimator.estimate_text("你好世界")
        assert tokens > 0

    def test_estimate_message(self):
        """测试消息估算。"""
        estimator = TokenEstimator()
        message = Message(
            role="user",
            content=[TextContent(text="测试消息")],
        )
        tokens = estimator.estimate_message(message)
        assert tokens > 0

    def test_estimate_messages(self):
        """测试消息列表估算。"""
        estimator = TokenEstimator()
        messages = [
            Message(role="user", content=[TextContent(text="你好")]),
            Message(role="assistant", content=[TextContent(text="你好！")]),
        ]
        total = estimator.estimate_messages(messages)
        assert total > 0

    def test_estimate_tool_use(self):
        """测试工具调用估算。"""
        estimator = TokenEstimator()
        content = ToolUseContent(
            id="call-1",
            name="search",
            input={"query": "test"},
        )
        tokens = estimator.estimate_content_block(content)
        assert tokens > 0

    def test_estimate_tool_result(self):
        """测试工具结果估算。"""
        estimator = TokenEstimator()
        content = ToolResultContent(
            tool_use_id="call-1",
            content="结果内容",
        )
        tokens = estimator.estimate_content_block(content)
        assert tokens > 0


# ── ContextCompressor 测试 ──────────────────────────────────────────────

class TestContextCompressor:
    """ContextCompressor 测试。"""

    def test_create_compressor(self):
        """测试创建压缩器。"""
        compressor = ContextCompressor()
        assert compressor is not None

    def test_should_compress_false(self):
        """测试不需要压缩。"""
        compressor = ContextCompressor()
        compressor._max_tokens = 100000  # 设置很大的限制

        messages = [
            Message(role="user", content=[TextContent(text="测试")]),
        ]

        assert not compressor.should_compress(messages)

    def test_get_protection_regions(self):
        """测试获取保护区域。"""
        compressor = ContextCompressor()
        compressor._protect_head = 2
        compressor._protect_tail = 2

        messages = [
            Message(role="system", content=[TextContent(text="系统")]),
            Message(role="user", content=[TextContent(text="用户1")]),
            Message(role="assistant", content=[TextContent(text="回复1")]),
            Message(role="user", content=[TextContent(text="用户2")]),
            Message(role="assistant", content=[TextContent(text="回复2")]),
        ]

        regions = compressor.get_protection_regions(messages)
        assert len(regions) == 2

    def test_is_protected(self):
        """测试保护区域检查。"""
        from agentforge.context.compressor import ProtectionRegion

        compressor = ContextCompressor()
        regions = [
            ProtectionRegion(start=0, end=2, priority=10),
            ProtectionRegion(start=3, end=5, priority=8),
        ]

        assert compressor.is_protected(0, regions)
        assert compressor.is_protected(1, regions)
        assert not compressor.is_protected(2, regions)
        assert compressor.is_protected(3, regions)

    def test_compress_empty_messages(self):
        """测试压缩空消息列表。"""
        compressor = ContextCompressor()
        result = compressor.compress([])
        assert result == []

    def test_compress_small_messages(self):
        """测试压缩小消息列表。"""
        compressor = ContextCompressor()

        messages = [
            Message(role="user", content=[TextContent(text="测试")]),
        ]

        result = compressor.compress(messages)
        assert len(result) == 1


# ── 集成测试 ──────────────────────────────────────────────

class TestP4Integration:
    """P4 阶段集成测试。"""

    def test_message_manager_with_compressor(self):
        """测试消息管理器与压缩器集成。"""
        settings = create_settings()
        compressor = ContextCompressor()
        manager = MessageManager(settings, compressor=compressor)

        manager.add_user_message("测试消息")

        context = manager.get_context()
        assert len(context) == 1

    def test_full_workflow(self):
        """测试完整工作流。"""
        settings = create_settings()

        # 创建组件
        manager = MessageManager(settings)
        orchestrator = ToolOrchestrator(settings)

        # 添加消息
        manager.add_user_message("你好")

        # 获取上下文
        context = manager.get_context()
        assert len(context) == 1

        # 清理
        orchestrator.shutdown()
