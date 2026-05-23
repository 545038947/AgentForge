"""异步 API 测试。"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from hai_agent.agent import Agent
from hai_agent.types import NormalizedResponse, StreamDelta, Usage
from hai_agent.tools import FunctionTool
from hai_agent.tools.executor import ToolExecutor
from hai_agent.delegation.manager import DelegationManager, DelegationStrategy


class TestAgentAsync:
    """测试 Agent 异步方法。"""

    def test_run_async_basic(self):
        """测试基本异步运行。"""
        async def run_test():
            # 创建 mock provider
            mock_provider = MagicMock()
            mock_provider.name = "mock"
            mock_provider.capabilities.supports_tools = True
            mock_provider.capabilities.supports_streaming = True

            # mock complete 方法返回有效响应
            mock_provider.complete.return_value = NormalizedResponse(
                content="Hello async",
                finish_reason="stop",
            )

            agent = Agent(provider=mock_provider)

            response = await agent.run_async("你好")

            assert response is not None
            assert "Hello async" in response.content

        asyncio.run(run_test())

    def test_stream_async_basic(self):
        """测试基本异步流式响应。"""
        async def run_test():
            # 创建 mock provider
            mock_provider = MagicMock()
            mock_provider.capabilities.supports_tools = True
            mock_provider.capabilities.supports_streaming = True
            mock_provider.stream.return_value = iter([
                NormalizedResponse(content="Hello"),
                NormalizedResponse(content="Hello world"),
            ])

            agent = Agent(provider=mock_provider)

            chunks = []
            async for chunk in agent.stream_async("你好"):
                chunks.append(chunk)

            assert len(chunks) == 2
            assert chunks[-1].content == "Hello world"

        asyncio.run(run_test())

    def test_stream_deltas_async_basic(self):
        """测试基本异步增量流式响应。"""
        async def run_test():
            # 创建 mock provider
            mock_provider = MagicMock()
            mock_provider.capabilities.supports_tools = True
            mock_provider.capabilities.supports_streaming = True
            mock_provider.stream.return_value = iter([
                NormalizedResponse(content="Hello"),
                NormalizedResponse(content="Hello world"),
            ])

            agent = Agent(provider=mock_provider)

            deltas = []
            async for delta in agent.stream_deltas_async("你好"):
                deltas.append(delta)

            # 应该至少有一个增量
            assert len(deltas) >= 1

        asyncio.run(run_test())

    def test_complete_async(self):
        """测试异步完成调用。"""
        async def run_test():
            # 创建 mock provider
            mock_provider = MagicMock()
            mock_provider.capabilities.supports_tools = True
            mock_provider.capabilities.supports_streaming = True
            mock_provider.complete.return_value = NormalizedResponse(
                content="Response",
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

            agent = Agent(provider=mock_provider)

            response = await agent.complete_async([])

            assert response.content == "Response"
            assert response.usage.total_tokens == 15

        asyncio.run(run_test())


class TestToolExecutorAsync:
    """测试 ToolExecutor 异步方法。"""

    def test_execute_async(self):
        """测试异步执行单个工具。"""
        async def run_test():
            # 创建 mock 工具
            mock_tool = MagicMock()
            mock_tool.name = "test_tool"
            mock_tool.timeout = 30.0
            mock_tool.execute.return_value = MagicMock(
                tool_call_id="call-1",
                content="result",
                is_error=False,
            )

            executor = ToolExecutor()
            executor.start()

            try:
                result = await executor.execute_async(mock_tool, "call-1", query="test")
                assert result.content == "result"
            finally:
                executor.shutdown()

        asyncio.run(run_test())

    def test_execute_batch_async(self):
        """测试异步并发执行多个工具。"""
        async def run_test():
            # 创建 mock 工具
            mock_tool1 = MagicMock()
            mock_tool1.name = "tool1"
            mock_tool1.timeout = 30.0
            mock_tool1.execute.return_value = MagicMock(
                tool_call_id="call-1",
                content="result1",
                is_error=False,
            )

            mock_tool2 = MagicMock()
            mock_tool2.name = "tool2"
            mock_tool2.timeout = 30.0
            mock_tool2.execute.return_value = MagicMock(
                tool_call_id="call-2",
                content="result2",
                is_error=False,
            )

            executor = ToolExecutor()
            executor.start()

            try:
                results = await executor.execute_batch_async([
                    (mock_tool1, "call-1", {"query": "a"}),
                    (mock_tool2, "call-2", {"query": "b"}),
                ])

                assert len(results) == 2
                assert results[0].content == "result1"
                assert results[1].content == "result2"
            finally:
                executor.shutdown()

        asyncio.run(run_test())


class TestDelegationManagerAsync:
    """测试 DelegationManager 异步方法。"""

    def test_delegate_async(self):
        """测试异步单任务委托。"""
        async def run_test():
            from hai_agent.delegation.config import DelegationConfig

            # 创建配置
            config = DelegationConfig()

            manager = DelegationManager(config=config)

            # 由于没有真正的 Agent，delegate 会返回模拟结果
            result = await manager.delegate_async(goal="测试任务")

            assert result is not None

        asyncio.run(run_test())

    def test_delegate_batch_async_sequential(self):
        """测试异步批量委托（顺序策略）。"""
        async def run_test():
            from hai_agent.delegation.config import TaskSpec, DelegationConfig

            config = DelegationConfig()
            manager = DelegationManager(config=config)

            tasks = [
                TaskSpec(goal="任务1"),
                TaskSpec(goal="任务2"),
            ]

            result = await manager.delegate_batch_async(
                tasks,
                strategy=DelegationStrategy.SEQUENTIAL,
            )

            assert result is not None

        asyncio.run(run_test())


class TestAsyncUtils:
    """测试异步工具函数。"""

    def test_to_thread(self):
        """测试 to_thread 函数。"""
        from hai_agent.core.async_utils import to_thread

        async def run_test():
            def sync_func(x):
                return x * 2

            result = await to_thread(sync_func, 5)
            assert result == 10

        asyncio.run(run_test())

    def test_gather_with_concurrency(self):
        """测试并发限制的 gather。"""
        from hai_agent.core.async_utils import gather_with_concurrency

        async def run_test():
            async def slow_task(i):
                await asyncio.sleep(0.01)
                return i

            results = await gather_with_concurrency(2, slow_task(1), slow_task(2), slow_task(3))
            assert results == [1, 2, 3]

        asyncio.run(run_test())

    def test_is_async_context(self):
        """测试异步上下文检测。"""
        from hai_agent.core.async_utils import is_async_context

        # 同步上下文
        assert is_async_context() is False

        # 异步上下文
        async def check():
            assert is_async_context() is True

        asyncio.run(check())

    def test_async_wrap_decorator(self):
        """测试 async_wrap 装饰器。"""
        from hai_agent.core.async_utils import async_wrap

        @async_wrap
        def sync_function(x):
            return x * 2

        async def run_test():
            result = await sync_function(5)
            assert result == 10

        asyncio.run(run_test())


class TestAsyncIteratorWrapper:
    """测试异步迭代器包装器。"""

    def test_basic_iteration(self):
        """测试基本迭代。"""
        from hai_agent.core.async_utils import AsyncIteratorWrapper

        async def run_test():
            sync_iter = iter([1, 2, 3])
            async_iter = AsyncIteratorWrapper(sync_iter)

            results = []
            async for item in async_iter:
                results.append(item)

            assert results == [1, 2, 3]

        asyncio.run(run_test())

    def test_empty_iterator(self):
        """测试空迭代器。"""
        from hai_agent.core.async_utils import AsyncIteratorWrapper

        async def run_test():
            sync_iter = iter([])
            async_iter = AsyncIteratorWrapper(sync_iter)

            results = []
            async for item in async_iter:
                results.append(item)

            assert results == []

        asyncio.run(run_test())
