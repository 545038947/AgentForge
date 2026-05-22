"""异步工具模块。

提供同步/异步桥接的安全调度函数，参考 hermes-agent 的 async_utils 设计。
"""

from __future__ import annotations

import asyncio
import functools
import logging
from concurrent.futures import Future
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def safe_schedule_threadsafe(
    coro: Coroutine[Any, Any, T],
    loop: Optional[asyncio.AbstractEventLoop],
) -> Optional[Future]:
    """在指定事件循环上安全调度协程。

    从同步上下文调度协程到异步事件循环。
    在所有失败路径中都会关闭协程，避免 "coroutine was never awaited" 警告。

    Args:
        coro: 要调度的协程
        loop: 目标事件循环

    Returns:
        Future 对象，失败返回 None
    """
    if loop is None:
        if asyncio.iscoroutine(coro):
            coro.close()
        return None

    try:
        return asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception:
        if asyncio.iscoroutine(coro):
            coro.close()
        return None


async def to_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """在线程池中运行同步函数。

    asyncio.to_thread 的包装，提供更好的错误处理。

    Args:
        func: 同步函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数返回值
    """
    return await asyncio.to_thread(func, *args, **kwargs)


async def gather_with_concurrency(
    limit: int,
    *coros: Coroutine[Any, Any, T],
) -> list[T]:
    """限制并发数的 gather。

    Args:
        limit: 最大并发数
        *coros: 协程列表

    Returns:
        结果列表
    """
    semaphore = asyncio.Semaphore(limit)

    async def limited(coro: Coroutine[Any, Any, T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(*[limited(coro) for coro in coros])


async def run_with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout: float,
    default: Optional[T] = None,
) -> Optional[T]:
    """带超时运行协程。

    Args:
        coro: 协程
        timeout: 超时时间（秒）
        default: 超时时返回的默认值

    Returns:
        协程返回值，超时返回 default
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.debug(f"协程执行超时（{timeout}秒）")
        return default


def is_async_context() -> bool:
    """检查当前是否在异步上下文中。

    Returns:
        True 如果在异步上下文中
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def get_event_loop() -> Optional[asyncio.AbstractEventLoop]:
    """获取事件循环。

    优先返回运行中的循环，否则返回 None。

    Returns:
        事件循环，不存在返回 None
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class AsyncIteratorWrapper:
    """同步迭代器的异步包装器。

    将同步 Iterator 包装为 AsyncIterator。

    使用示例：
        sync_iter = iter([1, 2, 3])
        async_iter = AsyncIteratorWrapper(sync_iter)
        async for item in async_iter:
            print(item)
    """

    def __init__(self, iterator: Any, loop: Optional[asyncio.AbstractEventLoop] = None):
        """初始化包装器。

        Args:
            iterator: 同步迭代器
            loop: 事件循环（可选，默认自动获取）
        """
        self._iterator = iterator
        self._loop = loop

    def __aiter__(self) -> "AsyncIteratorWrapper":
        return self

    async def __anext__(self) -> Any:
        """异步获取下一个元素。"""
        loop = self._loop or get_event_loop()
        if loop is None:
            # 没有事件循环，直接同步获取
            try:
                return next(self._iterator)
            except StopIteration:
                raise StopAsyncIteration

        # 在线程池中获取下一个元素
        try:
            item = await loop.run_in_executor(None, lambda: next(self._iterator, None))
            if item is None:
                raise StopAsyncIteration
            return item
        except StopIteration:
            raise StopAsyncIteration


def async_wrap(func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
    """将同步函数包装为异步函数。

    装饰器形式：

    @async_wrap
    def sync_function():
        return "result"

    async def main():
        result = await sync_function()

    Args:
        func: 同步函数

    Returns:
        异步函数
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper
