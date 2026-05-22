"""重试工具。

提供抖动指数退避，防止多个会话同时重试造成的惊群效应。
参考 hermes-agent/agent/retry_utils.py。
"""

from __future__ import annotations

import random
import threading
import time
from typing import Optional


# 单调计数器用于抖动种子唯一性
_jitter_counter = 0
_jitter_lock = threading.Lock()


def jittered_backoff(
    attempt: int,
    *,
    base_delay: float = 5.0,
    max_delay: float = 120.0,
    jitter_ratio: float = 0.5,
) -> float:
    """计算抖动指数退避延迟。

    Args:
        attempt: 1 基础的重试尝试次数
        base_delay: 第一次尝试的基础延迟（秒）
        max_delay: 最大延迟上限（秒）
        jitter_ratio: 抖动比例（0.5 表示抖动在 [0, 0.5 * delay] 范围内）

    Returns:
        延迟秒数: min(base * 2^(attempt-1), max_delay) + jitter

    抖动使并发重试去相关，避免多个会话同时重试同一 Provider。
    """
    global _jitter_counter
    with _jitter_lock:
        _jitter_counter += 1
        tick = _jitter_counter

    exponent = max(0, attempt - 1)
    if exponent >= 63 or base_delay <= 0:
        delay = max_delay
    else:
        delay = min(base_delay * (2 ** exponent), max_delay)

    # 使用时间 + 计数器作为种子，即使时钟粗糙也能去相关
    seed = (time.time_ns() ^ (tick * 0x9E3779B9)) & 0xFFFFFFFF
    rng = random.Random(seed)
    jitter = rng.uniform(0, jitter_ratio * delay)

    return delay + jitter


class RetryPolicy:
    """重试策略配置。

    定义重试行为：最大次数、退避参数、可重试条件等。
    """

    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 5.0,
        max_delay: float = 120.0,
        jitter_ratio: float = 0.5,
        retryable_exceptions: Optional[tuple] = None,
    ):
        """初始化重试策略。

        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            jitter_ratio: 抖动比例
            retryable_exceptions: 可重试的异常类型元组
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_ratio = jitter_ratio
        self.retryable_exceptions = retryable_exceptions or ()

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该重试。

        Args:
            error: 发生的异常
            attempt: 当前尝试次数

        Returns:
            True 如果应该重试
        """
        if attempt >= self.max_retries:
            return False

        # 检查异常类型
        if isinstance(error, self.retryable_exceptions):
            return True

        # 默认不重试
        return True  # 由 classify_api_error 决定

    def get_delay(self, attempt: int) -> float:
        """获取重试延迟。

        Args:
            attempt: 当前尝试次数

        Returns:
            延迟秒数
        """
        return jittered_backoff(
            attempt,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            jitter_ratio=self.jitter_ratio,
        )


class RetryContext:
    """重试上下文。

    跟踪重试状态、延迟、错误历史。
    """

    def __init__(self, policy: Optional[RetryPolicy] = None):
        """初始化重试上下文。

        Args:
            policy: 重试策略
        """
        self.policy = policy or RetryPolicy()
        self.attempt = 0
        self.errors: list[Exception] = []
        self.total_delay = 0.0

    def record_error(self, error: Exception) -> bool:
        """记录错误并决定是否重试。

        Args:
            error: 发生的异常

        Returns:
            True 如果应该重试
        """
        self.errors.append(error)
        self.attempt += 1
        return self.policy.should_retry(error, self.attempt)

    def get_delay(self) -> float:
        """获取下次重试延迟。"""
        delay = self.policy.get_delay(self.attempt)
        self.total_delay += delay
        return delay

    @property
    def last_error(self) -> Optional[Exception]:
        """获取最后一个错误。"""
        return self.errors[-1] if self.errors else None

    def reset(self) -> None:
        """重置上下文。"""
        self.attempt = 0
        self.errors.clear()
        self.total_delay = 0.0


def sleep_with_interrupt(
    seconds: float,
    interrupt_check: Optional[callable] = None,
    check_interval: float = 0.2,
) -> bool:
    """可中断的睡眠。

    Args:
        seconds: 睡眠秒数
        interrupt_check: 中断检查函数（返回 True 表示需要中断）
        check_interval: 检查间隔（秒）

    Returns:
        True 如果被中断，False 如果正常完成
    """
    end_time = time.time() + seconds

    while time.time() < end_time:
        if interrupt_check and interrupt_check():
            return True
        sleep_time = min(check_interval, end_time - time.time())
        if sleep_time > 0:
            time.sleep(sleep_time)

    return False


__all__ = [
    "jittered_backoff",
    "RetryPolicy",
    "RetryContext",
    "sleep_with_interrupt",
]
