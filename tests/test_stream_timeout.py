"""流式传输超时控制测试。"""

import time

import pytest

from agentforge.providers.stream_timeout import (
    StreamTimeoutError, stream_with_timeout,
)


class TestStreamWithTimeout:
    def test_normal_stream_passes_through(self):
        """正常流式传输不受超时影响。"""
        def gen():
            for i in range(5):
                yield i
        result = list(stream_with_timeout(gen(), timeout_seconds=10.0, idle_timeout=5.0))
        assert result == [0, 1, 2, 3, 4]

    def test_idle_timeout_triggers(self):
        """空闲超时触发 StreamTimeoutError。"""
        def slow_gen():
            yield "a"
            time.sleep(0.3)
            yield "b"
            time.sleep(1.5)  # 超过 idle_timeout
            yield "c"

        with pytest.raises(StreamTimeoutError, match="空闲超时"):
            list(stream_with_timeout(slow_gen(), timeout_seconds=10.0, idle_timeout=1.0))

    def test_total_timeout_triggers(self):
        """总超时触发 StreamTimeoutError。"""
        def slow_gen():
            for i in range(100):
                time.sleep(0.05)
                yield i

        with pytest.raises(StreamTimeoutError, match="总超时"):
            list(stream_with_timeout(slow_gen(), timeout_seconds=0.5, idle_timeout=5.0))

    def test_no_timeout_when_fast(self):
        """快速流式传输不触发超时。"""
        def fast_gen():
            for i in range(10):
                yield i
        result = list(stream_with_timeout(fast_gen(), timeout_seconds=1.0, idle_timeout=0.5))
        assert len(result) == 10

    def test_empty_generator(self):
        """空生成器不触发超时。"""
        def empty_gen():
            return
            yield
        result = list(stream_with_timeout(empty_gen(), timeout_seconds=1.0))
        assert result == []

    def test_stream_timeout_error_is_timeout(self):
        """StreamTimeoutError 是 TimeoutError 的子类。"""
        assert issubclass(StreamTimeoutError, TimeoutError)
