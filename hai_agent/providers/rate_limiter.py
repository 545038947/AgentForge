"""令牌桶速率限制器 — 控制对 Provider 的请求频率和 token 消耗。"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """速率限制配置。"""
    requests_per_minute: float = 60.0
    tokens_per_minute: float = 100000.0
    burst_size: int = 10


class TokenBucketRateLimiter:
    """令牌桶算法实现的速率限制器。

    两个桶：
    - requests_bucket: 控制请求频率
    - tokens_bucket: 控制 token 消耗频率
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self._config = config or RateLimitConfig()
        self._lock = threading.Lock()
        self._requests_tokens = float(self._config.burst_size)
        self._tokens_tokens = float(self._config.tokens_per_minute)
        self._requests_refill_rate = self._config.requests_per_minute / 60.0
        self._tokens_refill_rate = self._config.tokens_per_minute / 60.0
        self._last_refill = time.monotonic()

    def acquire(self, estimated_tokens: int = 0) -> float:
        """尝试获取请求许可。

        Args:
            estimated_tokens: 预估消耗的 token 数

        Returns:
            需要等待的秒数（0 表示无需等待）
        """
        with self._lock:
            self._refill()
            wait_time = 0.0

            if self._requests_tokens < 1.0:
                wait_time = max(wait_time, (1.0 - self._requests_tokens) / self._requests_refill_rate)

            if estimated_tokens > 0 and self._tokens_tokens < estimated_tokens:
                token_wait = (estimated_tokens - self._tokens_tokens) / self._tokens_refill_rate
                wait_time = max(wait_time, token_wait)

            return wait_time

    def consume(self, tokens_used: int = 0) -> None:
        """消耗令牌（请求完成后调用）。"""
        with self._lock:
            self._refill()
            self._requests_tokens = max(0, self._requests_tokens - 1.0)
            if tokens_used > 0:
                self._tokens_tokens = max(0, self._tokens_tokens - tokens_used)

    def wait_and_acquire(self, estimated_tokens: int = 0, max_wait: float = 30.0) -> bool:
        """等待并获取许可。

        Returns:
            True 表示获得许可，False 表示超过最大等待时间
        """
        wait_time = self.acquire(estimated_tokens)
        if wait_time > max_wait:
            logger.warning(f"速率限制等待时间 {wait_time:.1f}s 超过最大等待 {max_wait:.1f}s")
            return False
        if wait_time > 0:
            time.sleep(wait_time)
        self.consume(estimated_tokens)
        return True

    def _refill(self) -> None:
        """补充令牌。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now

        self._requests_tokens = min(
            self._config.burst_size,
            self._requests_tokens + elapsed * self._requests_refill_rate,
        )
        self._tokens_tokens = min(
            self._config.tokens_per_minute,
            self._tokens_tokens + elapsed * self._tokens_refill_rate,
        )

    @property
    def available_requests(self) -> float:
        """当前可用的请求令牌数。"""
        with self._lock:
            self._refill()
            return self._requests_tokens

    @property
    def available_tokens(self) -> float:
        """当前可用的 token 令牌数。"""
        with self._lock:
            self._refill()
            return self._tokens_tokens


class ProviderRateLimiter:
    """Provider 级别的速率限制管理器。

    每个 Provider 维护独立的速率限制器。
    """

    def __init__(self):
        self._limiters: Dict[str, TokenBucketRateLimiter] = {}
        self._lock = threading.Lock()

    def get_limiter(self, provider_name: str) -> TokenBucketRateLimiter:
        """获取指定 Provider 的速率限制器。"""
        with self._lock:
            if provider_name not in self._limiters:
                self._limiters[provider_name] = TokenBucketRateLimiter()
            return self._limiters[provider_name]

    def configure(self, provider_name: str, config: RateLimitConfig) -> None:
        """配置指定 Provider 的速率限制。"""
        with self._lock:
            self._limiters[provider_name] = TokenBucketRateLimiter(config)

    def wait_and_acquire(self, provider_name: str, estimated_tokens: int = 0, max_wait: float = 30.0) -> bool:
        """等待并获取指定 Provider 的请求许可。"""
        return self.get_limiter(provider_name).wait_and_acquire(estimated_tokens, max_wait)

    def consume(self, provider_name: str, tokens_used: int = 0) -> None:
        """消耗指定 Provider 的令牌。"""
        self.get_limiter(provider_name).consume(tokens_used)