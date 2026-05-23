"""并发场景测试。"""

import asyncio
import threading

import pytest
from unittest.mock import MagicMock

from agentforge import Agent
from agentforge.types import NormalizedResponse
from agentforge.managers.message import MessageManager
from agentforge.config.settings import Settings


def _make_mock_provider():
    """创建 Mock Provider。"""
    provider = MagicMock()
    provider.name = "mock"

    def mock_stream(messages, tools=None):
        yield NormalizedResponse(content="响应内容", finish_reason="stop")

    provider.stream.side_effect = mock_stream

    async def mock_stream_async(messages, tools=None):
        yield NormalizedResponse(content="响应内容", finish_reason="stop")

    provider.stream_async = mock_stream_async

    async def mock_run_async(messages, tools=None):
        return NormalizedResponse(content="响应内容", finish_reason="stop")

    provider.run_async = mock_run_async

    return provider


class TestConcurrentSessions:
    """多会话并发测试。"""

    def test_multiple_agents_isolated(self):
        """测试多个 Agent 实例的消息历史隔离。"""
        mock_provider = _make_mock_provider()
        agents = [
            Agent(provider=mock_provider, register_atexit=False)
            for _ in range(5)
        ]

        # 每个 Agent 添加不同的消息
        for i, agent in enumerate(agents):
            agent._message_manager.add_user_message(f"消息 {i}")

        # 验证消息历史隔离
        for i, agent in enumerate(agents):
            messages = agent._message_manager.get_messages()
            assert len(messages) == 1
            assert f"消息 {i}" in messages[0].content[0].text

    @pytest.mark.asyncio
    async def test_concurrent_run_async(self):
        """测试并发调用 run_async。"""
        mock_provider = _make_mock_provider()
        agent = Agent(provider=mock_provider, register_atexit=False)

        tasks = [
            agent.run_async(f"消息 {i}")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"任务 {i} 失败: {result}"

    @pytest.mark.asyncio
    async def test_concurrent_stream_async(self):
        """测试并发流式调用。"""
        mock_provider = _make_mock_provider()
        agent = Agent(provider=mock_provider, register_atexit=False)

        async def collect_stream(message):
            chunks = []
            async for chunk in agent.stream_async(message):
                chunks.append(chunk)
            return chunks

        tasks = [
            collect_stream(f"消息 {i}")
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"流式任务 {i} 失败: {result}"


class TestThreadSafety:
    """线程安全测试。"""

    def test_message_manager_thread_safety(self):
        """测试 MessageManager 线程安全。"""
        manager = MessageManager(Settings(model="test"))
        errors = []

        def add_messages(thread_id):
            try:
                for i in range(100):
                    manager.add_user_message(f"线程 {thread_id} 消息 {i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_messages, args=(i,))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"线程安全错误: {errors}"
        assert len(manager.get_messages()) == 1000  # 10 线程 * 100 消息
