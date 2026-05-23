"""速率限制器测试。"""

import time
import threading

from hai_agent.providers.rate_limiter import (
    RateLimitConfig, TokenBucketRateLimiter, ProviderRateLimiter,
)


class TestRateLimitConfig:
    def test_defaults(self):
        config = RateLimitConfig()
        assert config.requests_per_minute == 60.0
        assert config.tokens_per_minute == 100000.0
        assert config.burst_size == 10


class TestTokenBucketRateLimiter:
    def test_initial_burst_allowed(self):
        """初始突发请求应被允许。"""
        limiter = TokenBucketRateLimiter(RateLimitConfig(burst_size=5))
        for _ in range(5):
            wait = limiter.acquire()
            assert wait == 0.0
            limiter.consume()

    def test_rate_limit_kicks_in(self):
        """超过突发限制后应返回等待时间。"""
        limiter = TokenBucketRateLimiter(RateLimitConfig(
            requests_per_minute=6, burst_size=3
        ))
        for _ in range(3):
            limiter.consume()
        wait = limiter.acquire()
        assert wait > 0

    def test_tokens_refill_over_time(self):
        """令牌应随时间补充。"""
        limiter = TokenBucketRateLimiter(RateLimitConfig(
            requests_per_minute=60, burst_size=1
        ))
        limiter.consume()
        assert limiter.available_requests < 1.0
        time.sleep(1.1)
        assert limiter.available_requests >= 0.9

    def test_concurrent_access(self):
        """多线程并发访问应安全。"""
        limiter = TokenBucketRateLimiter(RateLimitConfig(
            requests_per_minute=600, burst_size=50
        ))
        errors = []

        def worker():
            try:
                for _ in range(10):
                    limiter.wait_and_acquire(max_wait=5.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_wait_and_acquire_success(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(burst_size=10))
        assert limiter.wait_and_acquire() is True

    def test_wait_and_acquire_timeout(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(
            requests_per_minute=0.1, burst_size=1
        ))
        limiter.consume()
        result = limiter.wait_and_acquire(max_wait=0.0)
        assert result is False

    def test_available_tokens_property(self):
        limiter = TokenBucketRateLimiter()
        assert limiter.available_tokens > 0

    def test_consume_tokens(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(tokens_per_minute=1000))
        limiter.consume(500)
        assert limiter.available_tokens < 1000


class TestProviderRateLimiter:
    def test_get_limiter_creates_default(self):
        mgr = ProviderRateLimiter()
        limiter = mgr.get_limiter("test")
        assert isinstance(limiter, TokenBucketRateLimiter)

    def test_get_limiter_same_provider(self):
        mgr = ProviderRateLimiter()
        l1 = mgr.get_limiter("ollama")
        l2 = mgr.get_limiter("ollama")
        assert l1 is l2

    def test_different_providers_independent(self):
        mgr = ProviderRateLimiter()
        l1 = mgr.get_limiter("ollama")
        l2 = mgr.get_limiter("openai")
        assert l1 is not l2

    def test_configure_custom(self):
        mgr = ProviderRateLimiter()
        config = RateLimitConfig(requests_per_minute=10, burst_size=2)
        mgr.configure("test", config)
        limiter = mgr.get_limiter("test")
        limiter.consume()
        limiter.consume()
        wait = limiter.acquire()
        assert wait > 0

    def test_wait_and_acquire_delegates(self):
        mgr = ProviderRateLimiter()
        assert mgr.wait_and_acquire("test") is True

    def test_consume_delegates(self):
        mgr = ProviderRateLimiter()
        mgr.consume("test", 100)
        assert mgr.get_limiter("test").available_tokens < 100000
