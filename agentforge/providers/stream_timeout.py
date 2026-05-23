"""流式传输超时控制 — 防止服务端无响应时无限挂起。"""

import logging
import time
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)


class StreamTimeoutError(TimeoutError):
    """流式传输超时错误。"""
    pass


def stream_with_timeout(
    generator: Generator,
    timeout_seconds: float = 120.0,
    idle_timeout: float = 30.0,
) -> Generator:
    """为同步流式生成器添加超时控制。

    Args:
        generator: 原始流式生成器
        timeout_seconds: 总超时（从第一个 chunk 开始计时）
        idle_timeout: 空闲超时（两个 chunk 之间的最大间隔）
    """
    last_chunk_ts = None
    start_ts = None

    for chunk in generator:
        now = time.monotonic()

        # 检查空闲超时
        if last_chunk_ts is not None and (now - last_chunk_ts) > idle_timeout:
            raise StreamTimeoutError(
                f"流式传输空闲超时: 超过 {idle_timeout}s 未收到数据"
            )

        # 检查总超时
        if start_ts is not None and (now - start_ts) > timeout_seconds:
            raise StreamTimeoutError(
                f"流式传输总超时: 超过 {timeout_seconds}s"
            )

        if start_ts is None:
            start_ts = now
        last_chunk_ts = now

        yield chunk


async def async_stream_with_timeout(
    async_generator: Any,
    timeout_seconds: float = 120.0,
    idle_timeout: float = 30.0,
) -> Any:
    """为异步流式生成器添加超时控制。"""
    last_chunk_ts = None
    start_ts = None

    async for chunk in async_generator:
        now = time.monotonic()

        if last_chunk_ts is not None and (now - last_chunk_ts) > idle_timeout:
            raise StreamTimeoutError(
                f"流式传输空闲超时: 超过 {idle_timeout}s 未收到数据"
            )

        if start_ts is not None and (now - start_ts) > timeout_seconds:
            raise StreamTimeoutError(
                f"流式传输总超时: 超过 {timeout_seconds}s"
            )

        if start_ts is None:
            start_ts = now
        last_chunk_ts = now

        yield chunk
