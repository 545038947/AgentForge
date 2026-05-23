# AgentForge P2 改进项实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 P2 改进项（MCP 连接复用、Prometheus 指标、流式超时、速率限制），提升框架生产环境可靠性和可观测性

**Architecture:**
- MCP 连接复用：在 MCPTool 中引入后台事件循环 + 连接池，替代每次调用的 `_execute_with_new_connection()`，保持同步接口不变
- Prometheus 指标：基于事件系统的订阅机制，新增 `MetricsCollector` 中间层 + 可选 `PrometheusExporter`
- 流式超时：在 Provider 基类的流式迭代器中添加 `asyncio.wait_for` / `threading.Event` 超时
- 速率限制：令牌桶算法实现 `RateLimiter`，嵌入 `RetryPolicy` 流程

**Tech Stack:** Python 3.9+, pytest, prometheus_client (可选依赖), asyncio

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `hai_agent/mcp/tool.py` | MCP 连接复用 | 修改 |
| `hai_agent/mcp/pool.py` | MCP 连接池 | 创建 |
| `hai_agent/mcp/manager.py` | 管理连接池生命周期 | 修改 |
| `hai_agent/metrics/collector.py` | 指标收集中间层 | 创建 |
| `hai_agent/metrics/prometheus.py` | Prometheus 导出器 | 创建 |
| `hai_agent/metrics/__init__.py` | 公开接口 | 创建 |
| `hai_agent/agent.py` | 集成 MetricsCollector | 修改 |
| `hai_agent/providers/base.py` | 流式超时 + 速率限制 | 修改 |
| `hai_agent/providers/rate_limiter.py` | 令牌桶速率限制器 | 创建 |
| `hai_agent/config/settings.py` | 新增配置项 | 修改 |
| `tests/test_mcp_pool.py` | 连接池测试 | 创建 |
| `tests/test_metrics.py` | 指标系统测试 | 创建 |
| `tests/test_rate_limiter.py` | 速率限制器测试 | 创建 |
| `tests/test_stream_timeout.py` | 流式超时测试 | 创建 |

---

## Task 1: MCP 连接池

**Files:**
- Create: `hai_agent/mcp/pool.py`
- Modify: `hai_agent/mcp/tool.py`
- Modify: `hai_agent/mcp/manager.py`
- Create: `tests/test_mcp_pool.py`

### 1.1 创建 MCP 连接池

- [ ] **Step 1: 创建 `hai_agent/mcp/pool.py`**

```python
"""MCP 连接池 — 复用已建立的 MCP 客户端连接。"""

import asyncio
import logging
import threading
import time
from typing import Dict, Optional

from .client import MCPClient, MCPClientConfig

logger = logging.getLogger(__name__)


class MCPConnectionPool:
    """管理 MCP 客户端连接的池化复用。

    在后台事件循环中保持连接活跃，避免每次调用创建新进程。
    线程安全：外部同步代码通过 run_coroutine_threadsafe 调用。
    """

    def __init__(
        self,
        max_idle_seconds: float = 300.0,
        max_connections: int = 10,
    ):
        self._max_idle_seconds = max_idle_seconds
        self._max_connections = max_connections
        self._clients: Dict[str, MCPClient] = {}
        self._last_used: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._started = False
        self._closed = False

    def start(self) -> None:
        """启动后台事件循环。"""
        with self._lock:
            if self._started:
                return
            self._loop_thread = threading.Thread(
                target=self._run_loop, daemon=True, name="mcp-pool"
            )
            self._loop_thread.start()
            # 等待循环启动
            while self._loop is None:
                time.sleep(0.01)
            self._started = True

    def _run_loop(self) -> None:
        """后台线程运行事件循环。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._idle_cleanup_loop())
        except Exception:
            logger.debug("MCP 连接池事件循环退出")
        finally:
            self._loop.close()

    async def _idle_cleanup_loop(self) -> None:
        """定期清理空闲连接。"""
        while not self._closed:
            await asyncio.sleep(60.0)
            if self._closed:
                break
            now = time.monotonic()
            to_remove = []
            for key, last in self._last_used.items():
                if now - last > self._max_idle_seconds:
                    to_remove.append(key)
            for key in to_remove:
                client = self._clients.pop(key, None)
                self._last_used.pop(key, None)
                if client and client.is_connected:
                    try:
                        await client.disconnect()
                        logger.debug(f"清理空闲 MCP 连接: {key}")
                    except Exception as e:
                        logger.warning(f"清理 MCP 连接失败: {key}: {e}")

    def get_or_create(self, config: MCPClientConfig) -> MCPClient:
        """获取或创建 MCP 客户端连接（同步接口）。

        使用连接配置的哈希作为池键，相同配置复用同一连接。
        """
        if not self._started:
            self.start()
        pool_key = self._config_key(config)
        with self._lock:
            if pool_key in self._clients:
                client = self._clients[pool_key]
                if client.is_connected:
                    self._last_used[pool_key] = time.monotonic()
                    return client
                # 连接已断开，移除后重建
                del self._clients[pool_key]
                self._last_used.pop(pool_key, None)
            # 超过最大连接数，清理最旧的
            if len(self._clients) >= self._max_connections:
                oldest_key = min(self._last_used, key=self._last_used.get)
                old_client = self._clients.pop(oldest_key, None)
                self._last_used.pop(oldest_key, None)
                if old_client and old_client.is_connected:
                    future = asyncio.run_coroutine_threadsafe(
                        old_client.disconnect(), self._loop
                    )
                    future.result(timeout=10.0)
        # 在后台循环中创建新连接
        client = MCPClient(config)
        future = asyncio.run_coroutine_threadsafe(
            client.connect(), self._loop
        )
        future.result(timeout=30.0)
        with self._lock:
            self._clients[pool_key] = client
            self._last_used[pool_key] = time.monotonic()
        return client

    def call_tool(self, config: MCPClientConfig, tool_name: str, arguments: dict) -> str:
        """通过连接池调用 MCP 工具（同步接口）。"""
        client = self.get_or_create(config)
        future = asyncio.run_coroutine_threadsafe(
            client.call_tool(tool_name, arguments), self._loop
        )
        return future.result(timeout=60.0)

    def shutdown(self) -> None:
        """关闭所有连接并停止事件循环。"""
        if self._closed:
            return
        self._closed = True
        if self._loop and not self._loop.is_closed():
            async def _close_all():
                for key, client in list(self._clients.items()):
                    try:
                        if client.is_connected:
                            await client.disconnect()
                    except Exception:
                        pass
                self._clients.clear()
                self._last_used.clear()
            future = asyncio.run_coroutine_threadsafe(_close_all(), self._loop)
            try:
                future.result(timeout=10.0)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)

    @staticmethod
    def _config_key(config: MCPClientConfig) -> str:
        """根据配置生成池键。"""
        if hasattr(config, 'command'):
            cmd = getattr(config, 'command', '')
            args = getattr(config, 'args', [])
            return f"cmd:{cmd}:{','.join(args)}"
        return f"cfg:{id(config)}"
```

- [ ] **Step 2: 修改 `hai_agent/mcp/tool.py` — 使用连接池**

当前 `MCPTool.execute()` (行 52-116) 调用 `_execute_with_new_connection()`。修改为优先使用连接池，回退到旧路径。

在 `MCPTool.__init__` 或类属性中添加 `_pool` 类变量：

```python
# 文件顶部添加
from .pool import MCPConnectionPool

class MCPTool(Tool):
    _pool: Optional[MCPConnectionPool] = None

    @classmethod
    def set_pool(cls, pool: MCPConnectionPool) -> None:
        cls._pool = pool

    @classmethod
    def get_pool(cls) -> Optional[MCPConnectionPool]:
        return cls._pool
```

修改 `execute()` 方法（行 52-116），在 `try` 块开头添加连接池路径：

```python
def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
    # 优先使用连接池
    if self._pool is not None:
        try:
            result = self._pool.call_tool(
                self._client.config, self.name, kwargs
            )
            return ToolResult(
                tool_call_id=tool_call_id,
                content=str(result),
                is_error=False,
            )
        except Exception as e:
            logger.warning(f"连接池调用失败，回退到新建连接: {e}")
    # 原有逻辑 — 在新线程中创建新连接
    ...
```

- [ ] **Step 3: 修改 `hai_agent/mcp/manager.py` — 管理连接池生命周期**

在 `MCPManager.__init__` 中初始化连接池，在 `shutdown` 中关闭：

```python
from .pool import MCPConnectionPool

class MCPManager:
    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._tools: Dict[str, MCPTool] = {}
        self._pool = MCPConnectionPool()
        MCPTool.set_pool(self._pool)

    def shutdown(self) -> None:
        # ... 原有清理代码 ...
        self._pool.shutdown()
        MCPTool.set_pool(None)
```

- [ ] **Step 4: 创建 `tests/test_mcp_pool.py`**

```python
"""MCP 连接池测试。"""

import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from hai_agent.mcp.pool import MCPConnectionPool
from hai_agent.mcp.client import MCPClientConfig


class TestMCPConnectionPoolInit:
    def test_init_defaults(self):
        pool = MCPConnectionPool()
        assert pool._max_idle_seconds == 300.0
        assert pool._max_connections == 10
        assert not pool._started

    def test_init_custom(self):
        pool = MCPConnectionPool(max_idle_seconds=60, max_connections=5)
        assert pool._max_idle_seconds == 60
        assert pool._max_connections == 5


class TestMCPConnectionPoolLifecycle:
    def test_start_creates_loop(self):
        pool = MCPConnectionPool()
        pool.start()
        assert pool._started
        assert pool._loop is not None
        pool.shutdown()

    def test_start_idempotent(self):
        pool = MCPConnectionPool()
        pool.start()
        pool.start()  # 第二次不应创建新线程
        pool.shutdown()

    def test_shutdown_closes_loop(self):
        pool = MCPConnectionPool()
        pool.start()
        pool.shutdown()
        assert pool._closed

    def test_shutdown_idempotent(self):
        pool = MCPConnectionPool()
        pool.start()
        pool.shutdown()
        pool.shutdown()  # 不应抛异常


class TestMCPConnectionPoolConfigKey:
    def test_config_key_deterministic(self):
        config = MagicMock()
        config.command = "python"
        config.args = ["server.py"]
        key1 = MCPConnectionPool._config_key(config)
        key2 = MCPConnectionPool._config_key(config)
        assert key1 == key2

    def test_config_key_different_args(self):
        config1 = MagicMock()
        config1.command = "python"
        config1.args = ["server1.py"]
        config2 = MagicMock()
        config2.command = "python"
        config2.args = ["server2.py"]
        key1 = MCPConnectionPool._config_key(config1)
        key2 = MCPConnectionPool._config_key(config2)
        assert key1 != key2


class TestMCPConnectionPoolMocked:
    """使用 Mock 测试连接池逻辑（不需要真实 MCP 服务）。"""

    def test_get_or_create_new_connection(self):
        pool = MCPConnectionPool()
        config = MagicMock()
        config.command = "python"
        config.args = ["test.py"]

        mock_client = MagicMock()
        mock_client.is_connected = True

        with patch("hai_agent.mcp.pool.MCPClient", return_value=mock_client):
            with patch.object(pool, "_loop") as mock_loop:
                # 模拟 asyncio.run_coroutine_threadsafe
                mock_future = MagicMock()
                mock_future.result.return_value = None
                with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                    pool._started = True
                    pool._loop = mock_loop
                    client = pool.get_or_create(config)
                    assert client is mock_client

        pool.shutdown()

    def test_get_or_create_reuses_existing(self):
        pool = MCPConnectionPool()
        config = MagicMock()
        config.command = "python"
        config.args = ["test.py"]

        mock_client = MagicMock()
        mock_client.is_connected = True
        pool._started = True
        pool._loop = MagicMock()

        # 手动注入已有连接
        key = pool._config_key(config)
        pool._clients[key] = mock_client
        pool._last_used[key] = time.monotonic()

        client = pool.get_or_create(config)
        assert client is mock_client
        pool.shutdown()

    def test_call_tool_uses_pool(self):
        pool = MCPConnectionPool()
        config = MagicMock()
        config.command = "python"
        config.args = ["test.py"]

        with patch.object(pool, "get_or_create") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client

            mock_future = MagicMock()
            mock_future.result.return_value = "工具执行结果"

            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                pool._started = True
                pool._loop = MagicMock()
                result = pool.call_tool(config, "search", {"q": "test"})
                assert result == "工具执行结果"

        pool.shutdown()
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_mcp_pool.py -v --tb=short`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add hai_agent/mcp/pool.py hai_agent/mcp/tool.py hai_agent/mcp/manager.py tests/test_mcp_pool.py
git commit -m "feat: MCP 连接池 — 复用已建立的客户端连接，避免每次调用启动新进程"
```

---

## Task 2: 指标收集中间层

**Files:**
- Create: `hai_agent/metrics/__init__.py`
- Create: `hai_agent/metrics/collector.py`
- Create: `tests/test_metrics.py`

### 2.1 创建 MetricsCollector

- [ ] **Step 1: 创建 `hai_agent/metrics/__init__.py`**

```python
"""AgentForge 指标系统。"""

from .collector import MetricsCollector

__all__ = ["MetricsCollector"]
```

- [ ] **Step 2: 创建 `hai_agent/metrics/collector.py`**

```python
"""指标收集中间层 — 订阅事件系统，聚合运行时指标。"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetrics:
    """单个 Provider 的指标。"""
    total_requests: int = 0
    total_errors: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_latency_ms: float = 0.0
    last_request_ts: float = 0.0
    by_error_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return 1.0 - (self.total_errors / self.total_requests)

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests


@dataclass
class ToolMetrics:
    """单个工具的指标。"""
    total_calls: int = 0
    total_errors: int = 0
    total_latency_ms: float = 0.0
    last_call_ts: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency_ms / self.total_calls


@dataclass
class SessionMetrics:
    """会话级别的指标。"""
    total_turns: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    session_start_ts: float = field(default_factory=time.monotonic)


class MetricsCollector:
    """通过订阅事件系统收集运行时指标。

    使用方式：
        collector = MetricsCollector()
        agent._event_dispatcher.on(EventType.PROVIDER_RESPONSE, collector.on_provider_response)
        agent._event_dispatcher.on(EventType.TOOL_END, collector.on_tool_end)

    指标可通过 get_snapshot() 获取快照，或通过 PrometheusExporter 导出。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: Dict[str, ProviderMetrics] = defaultdict(ProviderMetrics)
        self._tools: Dict[str, ToolMetrics] = defaultdict(ToolMetrics)
        self._session = SessionMetrics()
        self._exporters: List[Any] = []

    def add_exporter(self, exporter: Any) -> None:
        """添加指标导出器。导出器需实现 export(snapshot) 方法。"""
        self._exporters.append(exporter)

    def on_provider_response(self, event: Any) -> None:
        """处理 Provider 响应事件。"""
        provider_name = getattr(event, "provider_name", "unknown")
        usage = getattr(event, "usage", None)
        latency_ms = getattr(event, "latency_ms", 0.0)
        is_error = getattr(event, "is_error", False)
        error_type = getattr(event, "error_type", None)

        with self._lock:
            pm = self._providers[provider_name]
            pm.total_requests += 1
            pm.total_latency_ms += latency_ms
            pm.last_request_ts = time.monotonic()
            if is_error:
                pm.total_errors += 1
                if error_type:
                    pm.by_error_type[error_type] += 1
            if usage:
                pm.total_tokens_in += getattr(usage, "prompt_tokens", 0)
                pm.total_tokens_out += getattr(usage, "completion_tokens", 0)
                self._session.total_tokens_in += getattr(usage, "prompt_tokens", 0)
                self._session.total_tokens_out += getattr(usage, "completion_tokens", 0)

    def on_provider_error(self, event: Any) -> None:
        """处理 Provider 错误事件。"""
        provider_name = getattr(event, "provider_name", "unknown")
        error_type = getattr(event, "error_type", "unknown")
        latency_ms = getattr(event, "latency_ms", 0.0)

        with self._lock:
            pm = self._providers[provider_name]
            pm.total_requests += 1
            pm.total_errors += 1
            pm.total_latency_ms += latency_ms
            pm.last_request_ts = time.monotonic()
            pm.by_error_type[error_type] += 1

    def on_tool_end(self, event: Any) -> None:
        """处理工具执行结束事件。"""
        tool_name = getattr(event, "tool_name", "unknown")
        latency_ms = getattr(event, "latency_ms", 0.0)
        is_error = getattr(event, "is_error", False)

        with self._lock:
            tm = self._tools[tool_name]
            tm.total_calls += 1
            tm.total_latency_ms += latency_ms
            tm.last_call_ts = time.monotonic()
            if is_error:
                tm.total_errors += 1

    def on_turn_end(self, event: Any = None) -> None:
        """处理对话轮次结束事件。"""
        with self._lock:
            self._session.total_turns += 1

    def get_snapshot(self) -> Dict[str, Any]:
        """获取当前指标快照。"""
        with self._lock:
            return {
                "providers": {
                    name: {
                        "total_requests": m.total_requests,
                        "total_errors": m.total_errors,
                        "success_rate": m.success_rate,
                        "total_tokens_in": m.total_tokens_in,
                        "total_tokens_out": m.total_tokens_out,
                        "avg_latency_ms": m.avg_latency_ms,
                        "last_request_ts": m.last_request_ts,
                        "by_error_type": dict(m.by_error_type),
                    }
                    for name, m in self._providers.items()
                },
                "tools": {
                    name: {
                        "total_calls": m.total_calls,
                        "total_errors": m.total_errors,
                        "avg_latency_ms": m.avg_latency_ms,
                        "last_call_ts": m.last_call_ts,
                    }
                    for name, m in self._tools.items()
                },
                "session": {
                    "total_turns": self._session.total_turns,
                    "total_tokens_in": self._session.total_tokens_in,
                    "total_tokens_out": self._session.total_tokens_out,
                    "duration_seconds": time.monotonic() - self._session.session_start_ts,
                },
            }

    def reset(self) -> None:
        """重置所有指标。"""
        with self._lock:
            self._providers.clear()
            self._tools.clear()
            self._session = SessionMetrics()

    def export(self) -> None:
        """将指标推送到所有导出器。"""
        snapshot = self.get_snapshot()
        for exporter in self._exporters:
            try:
                exporter.export(snapshot)
            except Exception as e:
                logger.warning(f"指标导出失败: {e}")
```

- [ ] **Step 3: 创建 `tests/test_metrics.py`**

```python
"""指标系统测试。"""

import time
from unittest.mock import MagicMock

from hai_agent.metrics.collector import (
    MetricsCollector, ProviderMetrics, ToolMetrics, SessionMetrics,
)


class TestProviderMetrics:
    def test_success_rate_no_requests(self):
        m = ProviderMetrics()
        assert m.success_rate == 1.0

    def test_success_rate_with_errors(self):
        m = ProviderMetrics(total_requests=10, total_errors=2)
        assert m.success_rate == 0.8

    def test_avg_latency_no_requests(self):
        m = ProviderMetrics()
        assert m.avg_latency_ms == 0.0

    def test_avg_latency(self):
        m = ProviderMetrics(total_requests=2, total_latency_ms=200.0)
        assert m.avg_latency_ms == 100.0


class TestToolMetrics:
    def test_avg_latency_no_calls(self):
        m = ToolMetrics()
        assert m.avg_latency_ms == 0.0

    def test_avg_latency(self):
        m = ToolMetrics(total_calls=3, total_latency_ms=300.0)
        assert m.avg_latency_ms == 100.0


class TestMetricsCollectorProvider:
    def test_on_provider_response_success(self):
        collector = MetricsCollector()
        event = MagicMock()
        event.provider_name = "ollama"
        event.latency_ms = 150.0
        event.is_error = False
        event.error_type = None
        event.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        collector.on_provider_response(event)
        snapshot = collector.get_snapshot()
        assert snapshot["providers"]["ollama"]["total_requests"] == 1
        assert snapshot["providers"]["ollama"]["total_errors"] == 0
        assert snapshot["providers"]["ollama"]["total_tokens_in"] == 100
        assert snapshot["providers"]["ollama"]["total_tokens_out"] == 50

    def test_on_provider_response_error(self):
        collector = MetricsCollector()
        event = MagicMock()
        event.provider_name = "openai"
        event.latency_ms = 50.0
        event.is_error = True
        event.error_type = "rate_limit"
        event.usage = None

        collector.on_provider_response(event)
        snapshot = collector.get_snapshot()
        assert snapshot["providers"]["openai"]["total_requests"] == 1
        assert snapshot["providers"]["openai"]["total_errors"] == 1
        assert snapshot["providers"]["openai"]["by_error_type"]["rate_limit"] == 1

    def test_on_provider_error(self):
        collector = MetricsCollector()
        event = MagicMock()
        event.provider_name = "deepseek"
        event.error_type = "connection"
        event.latency_ms = 0.0

        collector.on_provider_error(event)
        snapshot = collector.get_snapshot()
        assert snapshot["providers"]["deepseek"]["total_errors"] == 1


class TestMetricsCollectorTool:
    def test_on_tool_end_success(self):
        collector = MetricsCollector()
        event = MagicMock()
        event.tool_name = "search"
        event.latency_ms = 200.0
        event.is_error = False

        collector.on_tool_end(event)
        snapshot = collector.get_snapshot()
        assert snapshot["tools"]["search"]["total_calls"] == 1
        assert snapshot["tools"]["search"]["total_errors"] == 0

    def test_on_tool_end_error(self):
        collector = MetricsCollector()
        event = MagicMock()
        event.tool_name = "calculator"
        event.latency_ms = 10.0
        event.is_error = True

        collector.on_tool_end(event)
        snapshot = collector.get_snapshot()
        assert snapshot["tools"]["calculator"]["total_errors"] == 1


class TestMetricsCollectorSession:
    def test_on_turn_end(self):
        collector = MetricsCollector()
        collector.on_turn_end()
        collector.on_turn_end()
        snapshot = collector.get_snapshot()
        assert snapshot["session"]["total_turns"] == 2

    def test_session_duration(self):
        collector = MetricsCollector()
        snapshot = collector.get_snapshot()
        assert snapshot["session"]["duration_seconds"] >= 0.0


class TestMetricsCollectorSnapshot:
    def test_snapshot_structure(self):
        collector = MetricsCollector()
        snapshot = collector.get_snapshot()
        assert "providers" in snapshot
        assert "tools" in snapshot
        assert "session" in snapshot

    def test_reset(self):
        collector = MetricsCollector()
        event = MagicMock()
        event.provider_name = "test"
        event.latency_ms = 100.0
        event.is_error = False
        event.error_type = None
        event.usage = None
        collector.on_provider_response(event)
        assert len(collector.get_snapshot()["providers"]) == 1

        collector.reset()
        assert len(collector.get_snapshot()["providers"]) == 0


class TestMetricsCollectorExporter:
    def test_add_and_call_exporter(self):
        collector = MetricsCollector()
        mock_exporter = MagicMock()
        collector.add_exporter(mock_exporter)
        collector.export()
        mock_exporter.export.assert_called_once()
        call_args = mock_exporter.export.call_args[0][0]
        assert "providers" in call_args
        assert "tools" in call_args
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_metrics.py -v --tb=short`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hai_agent/metrics/ tests/test_metrics.py
git commit -m "feat: 指标收集中间层 — 订阅事件系统，聚合运行时指标快照"
```

---

## Task 3: Prometheus 指标导出器

**Files:**
- Create: `hai_agent/metrics/prometheus.py`
- Modify: `hai_agent/metrics/__init__.py`
- Create: `tests/test_prometheus.py` (Mock prometheus_client)

### 3.1 创建 PrometheusExporter

- [ ] **Step 1: 创建 `hai_agent/metrics/prometheus.py`**

```python
"""Prometheus 指标导出器 — 将 MetricsCollector 快照暴露为 Prometheus 指标。

依赖：prometheus_client（可选，未安装时自动降级为日志输出）。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Info,
        CollectorRegistry, generate_latest,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    pass


class PrometheusExporter:
    """将指标快照导出为 Prometheus 格式。

    使用方式：
        exporter = PrometheusExporter(port=9090)
        collector.add_exporter(exporter)
        # 指标可通过 HTTP /metrics 端点或 generate_latest() 获取
    """

    def __init__(
        self,
        port: Optional[int] = None,
        registry: Optional[Any] = None,
        prefix: str = "agentforge",
    ):
        self._port = port
        self._prefix = prefix
        self._registry = registry
        self._server = None

        if not _PROMETHEUS_AVAILABLE:
            logger.info("prometheus_client 未安装，Prometheus 导出器降级为日志输出")
            self._counters: Dict[str, Any] = {}
            self._histograms: Dict[str, Any] = {}
            self._gauges: Dict[str, Any] = {}
            return

        reg = registry or CollectorRegistry()
        self._registry = reg

        self._provider_requests = Counter(
            f"{prefix}_provider_requests_total",
            "Total provider requests",
            ["provider"],
            registry=reg,
        )
        self._provider_errors = Counter(
            f"{prefix}_provider_errors_total",
            "Total provider errors",
            ["provider", "error_type"],
            registry=reg,
        )
        self._provider_latency = Histogram(
            f"{prefix}_provider_latency_ms",
            "Provider request latency",
            ["provider"],
            registry=reg,
        )
        self._provider_tokens_in = Counter(
            f"{prefix}_provider_tokens_in_total",
            "Total input tokens",
            ["provider"],
            registry=reg,
        )
        self._provider_tokens_out = Counter(
            f"{prefix}_provider_tokens_out_total",
            "Total output tokens",
            ["provider"],
            registry=reg,
        )
        self._tool_calls = Counter(
            f"{prefix}_tool_calls_total",
            "Total tool calls",
            ["tool"],
            registry=reg,
        )
        self._tool_errors = Counter(
            f"{prefix}_tool_errors_total",
            "Total tool errors",
            ["tool"],
            registry=reg,
        )
        self._tool_latency = Histogram(
            f"{prefix}_tool_latency_ms",
            "Tool call latency",
            ["tool"],
            registry=reg,
        )
        self._session_turns = Counter(
            f"{prefix}_session_turns_total",
            "Total session turns",
            registry=reg,
        )
        self._session_tokens_in = Counter(
            f"{prefix}_session_tokens_in_total",
            "Total session input tokens",
            registry=reg,
        )
        self._session_tokens_out = Counter(
            f"{prefix}_session_tokens_out_total",
            "Total session output tokens",
            registry=reg,
        )

    def export(self, snapshot: Dict[str, Any]) -> None:
        """从 MetricsCollector 快照更新 Prometheus 指标。"""
        if not _PROMETHEUS_AVAILABLE:
            logger.debug(f"指标快照（Prometheus 未安装）: {snapshot}")
            return

        for name, pm in snapshot.get("providers", {}).items():
            self._provider_requests.labels(provider=name).inc(pm.get("total_requests", 0))
            self._provider_errors.labels(provider=name, error_type="all").inc(pm.get("total_errors", 0))
            for etype, count in pm.get("by_error_type", {}).items():
                self._provider_errors.labels(provider=name, error_type=etype).inc(count)
            latency = pm.get("avg_latency_ms", 0.0)
            if latency > 0 and pm.get("total_requests", 0) > 0:
                self._provider_latency.labels(provider=name).observe(latency)
            self._provider_tokens_in.labels(provider=name).inc(pm.get("total_tokens_in", 0))
            self._provider_tokens_out.labels(provider=name).inc(pm.get("total_tokens_out", 0))

        for name, tm in snapshot.get("tools", {}).items():
            self._tool_calls.labels(tool=name).inc(tm.get("total_calls", 0))
            self._tool_errors.labels(tool=name).inc(tm.get("total_errors", 0))
            latency = tm.get("avg_latency_ms", 0.0)
            if latency > 0 and tm.get("total_calls", 0) > 0:
                self._tool_latency.labels(tool=name).observe(latency)

        sm = snapshot.get("session", {})
        self._session_turns.inc(sm.get("total_turns", 0))
        self._session_tokens_in.inc(sm.get("total_tokens_in", 0))
        self._session_tokens_out.inc(sm.get("total_tokens_out", 0))

    def start_http_server(self) -> None:
        """启动 Prometheus HTTP 服务端点。"""
        if not _PROMETHEUS_AVAILABLE:
            logger.warning("prometheus_client 未安装，无法启动 HTTP 服务")
            return
        if self._port and self._server is None:
            from prometheus_client import start_http_server
            start_http_server(self._port, registry=self._registry)
            logger.info(f"Prometheus 指标端点已启动: http://localhost:{self._port}/metrics")

    def get_metrics_text(self) -> str:
        """获取 Prometheus 文本格式指标（用于自定义 HTTP 端点）。"""
        if not _PROMETHEUS_AVAILABLE:
            return "# prometheus_client 未安装\n"
        return generate_latest(self._registry).decode("utf-8")
```

- [ ] **Step 2: 更新 `hai_agent/metrics/__init__.py`**

```python
"""AgentForge 指标系统。"""

from .collector import MetricsCollector
from .prometheus import PrometheusExporter

__all__ = ["MetricsCollector", "PrometheusExporter"]
```

- [ ] **Step 3: 创建 `tests/test_prometheus.py`**

```python
"""Prometheus 导出器测试。"""

from unittest.mock import MagicMock, patch

from hai_agent.metrics.prometheus import PrometheusExporter, _PROMETHEUS_AVAILABLE


class TestPrometheusExporterNoLib:
    """prometheus_client 未安装时的降级行为。"""

    def test_export_without_lib(self):
        """未安装时 export 不应抛异常。"""
        exporter = PrometheusExporter()
        snapshot = {
            "providers": {"test": {"total_requests": 1, "total_errors": 0,
                                   "avg_latency_ms": 0, "total_tokens_in": 0,
                                   "total_tokens_out": 0, "by_error_type": {}}},
            "tools": {},
            "session": {"total_turns": 1, "total_tokens_in": 0, "total_tokens_out": 0},
        }
        exporter.export(snapshot)  # 不应抛异常

    def test_get_metrics_text_without_lib(self):
        exporter = PrometheusExporter()
        text = exporter.get_metrics_text()
        assert "未安装" in text


class TestPrometheusExporterWithLib:
    """prometheus_client 已安装时的行为。"""

    def test_export_updates_counters(self):
        if not _PROMETHEUS_AVAILABLE:
            return  # 跳过，无可用的 prometheus_client

        exporter = PrometheusExporter()
        snapshot = {
            "providers": {
                "ollama": {
                    "total_requests": 5,
                    "total_errors": 1,
                    "avg_latency_ms": 150.0,
                    "total_tokens_in": 500,
                    "total_tokens_out": 250,
                    "by_error_type": {"rate_limit": 1},
                }
            },
            "tools": {
                "search": {
                    "total_calls": 10,
                    "total_errors": 2,
                    "avg_latency_ms": 100.0,
                    "last_call_ts": 0.0,
                }
            },
            "session": {
                "total_turns": 3,
                "total_tokens_in": 500,
                "total_tokens_out": 250,
            },
        }
        exporter.export(snapshot)
        text = exporter.get_metrics_text()
        assert "agentforge_provider_requests_total" in text
        assert "agentforge_tool_calls_total" in text
        assert "agentforge_session_turns_total" in text

    def test_get_metrics_text_format(self):
        if not _PROMETHEUS_AVAILABLE:
            return
        exporter = PrometheusExporter()
        text = exporter.get_metrics_text()
        assert isinstance(text, str)
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_prometheus.py tests/test_metrics.py -v --tb=short`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hai_agent/metrics/prometheus.py hai_agent/metrics/__init__.py tests/test_prometheus.py
git commit -m "feat: Prometheus 指标导出器 — 可选依赖，未安装时自动降级"
```

---

## Task 4: Agent 集成 MetricsCollector

**Files:**
- Modify: `hai_agent/agent.py`

### 4.1 在 Agent 中集成指标收集

- [ ] **Step 1: 修改 `hai_agent/agent.py`**

在 `Agent.__init__` 中添加 `metrics_collector` 参数：

```python
# 文件顶部添加导入
from hai_agent.metrics.collector import MetricsCollector

# Agent.__init__ 签名添加参数
def __init__(self, ..., metrics_collector: Optional[MetricsCollector] = None, ...):
    ...
    self._metrics_collector = metrics_collector or MetricsCollector()
    # 订阅事件
    self._bind_metrics_events()
```

添加 `_bind_metrics_events` 方法：

```python
def _bind_metrics_events(self) -> None:
    """将指标收集器绑定到事件系统。"""
    mc = self._metrics_collector
    self._event_dispatcher.on(EventType.PROVIDER_RESPONSE, mc.on_provider_response)
    self._event_dispatcher.on(EventType.TOOL_END, mc.on_tool_end)
```

在 `shutdown()` 中清理：

```python
# shutdown 末尾添加
if self._metrics_collector:
    self._metrics_collector.export()
```

在 `Agent` 类上暴露属性：

```python
@property
def metrics(self) -> MetricsCollector:
    """获取指标收集器。"""
    return self._metrics_collector
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_metrics.py tests/ -v --tb=short -x`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add hai_agent/agent.py
git commit -m "feat: Agent 集成 MetricsCollector — 自动订阅事件，暴露 metrics 属性"
```

---

## Task 5: 流式传输超时控制

**Files:**
- Create: `hai_agent/providers/stream_timeout.py`
- Modify: `hai_agent/providers/base.py`
- Create: `tests/test_stream_timeout.py`

### 5.1 创建流式超时包装器

- [ ] **Step 1: 创建 `hai_agent/providers/stream_timeout.py`**

```python
"""流式传输超时控制 — 防止服务端无响应时无限挂起。"""

import asyncio
import logging
import time
import threading
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
```

- [ ] **Step 2: 修改 `hai_agent/providers/base.py` — 在 stream 方法中应用超时**

在 `BaseProvider.stream()` 返回生成器时包装超时：

```python
# 文件顶部添加
from .stream_timeout import stream_with_timeout, StreamTimeoutError

# 在 stream 方法中，返回前包装
def stream(self, messages, **kwargs):
    # ... 原有逻辑获取 raw_generator ...
    stream_timeout = kwargs.pop("stream_timeout", None)
    stream_idle_timeout = kwargs.pop("stream_idle_timeout", None)

    # 原始生成器逻辑 ...

    if stream_timeout or stream_idle_timeout:
        return stream_with_timeout(
            raw_generator,
            timeout_seconds=stream_timeout or 120.0,
            idle_timeout=stream_idle_timeout or 30.0,
        )
    return raw_generator
```

**注意**：具体修改位置需要根据 `base.py` 的实际 `stream()` 方法调整。如果 `stream()` 是抽象方法或由子类实现，则在 `Agent.stream()` 中包装。

- [ ] **Step 3: 创建 `tests/test_stream_timeout.py`**

```python
"""流式传输超时控制测试。"""

import time

import pytest

from hai_agent.providers.stream_timeout import (
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
            time.sleep(0.5)
            yield "b"
            time.sleep(2.0)  # 超过 idle_timeout
            yield "c"

        with pytest.raises(StreamTimeoutError, match="空闲超时"):
            list(stream_with_timeout(slow_gen(), timeout_seconds=10.0, idle_timeout=1.0))

    def test_total_timeout_triggers(self):
        """总超时触发 StreamTimeoutError。"""
        def slow_gen():
            for i in range(100):
                time.sleep(0.1)
                yield i

        with pytest.raises(StreamTimeoutError, match="总超时"):
            list(stream_with_timeout(slow_gen(), timeout_seconds=1.0, idle_timeout=5.0))

    def test_no_timeout_when_fast(self):
        """快速流式传输不触发超时。"""
        def fast_gen():
            for i in range(10):
                yield i
        result = list(stream_with_timeout(fast_gen(), timeout_seconds=1.0, idle_timeout=0.1))
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
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_stream_timeout.py -v --tb=short`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hai_agent/providers/stream_timeout.py hai_agent/providers/base.py tests/test_stream_timeout.py
git commit -m "feat: 流式传输超时控制 — 防止服务端无响应时无限挂起"
```

---

## Task 6: Provider 速率限制器

**Files:**
- Create: `hai_agent/providers/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`
- Modify: `hai_agent/providers/base.py`

### 6.1 创建令牌桶速率限制器

- [ ] **Step 1: 创建 `hai_agent/providers/rate_limiter.py`**

```python
"""令牌桶速率限制器 — 控制对 Provider 的请求频率。"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """速率限制配置。"""
    requests_per_minute: float = 60.0
    tokens_per_minute: float = 100000.0
    burst_size: int = 10  # 允许的突发请求数


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

            # 检查请求桶
            if self._requests_tokens < 1.0:
                wait_time = max(wait_time, (1.0 - self._requests_tokens) / self._requests_refill_rate)

            # 检查 token 桶
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
```

- [ ] **Step 2: 创建 `tests/test_rate_limiter.py`**

```python
"""速率限制器测试。"""

import time
import threading

from hai_agent.providers.rate_limiter import (
    RateLimitConfig, TokenBucketRateLimiter,
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
        # 消耗初始令牌
        for _ in range(3):
            limiter.consume()
        # 下一个请求应需等待
        wait = limiter.acquire()
        assert wait > 0

    def test_tokens_refill_over_time(self):
        """令牌应随时间补充。"""
        limiter = TokenBucketRateLimiter(RateLimitConfig(
            requests_per_minute=60, burst_size=1
        ))
        limiter.consume()
        assert limiter.available_requests < 1.0
        # 等待补充
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
        # 等待时间会很长，max_wait 设为 0 立即返回
        result = limiter.wait_and_acquire(max_wait=0.0)
        assert result is False

    def test_available_tokens_property(self):
        limiter = TokenBucketRateLimiter()
        assert limiter.available_tokens > 0
```

- [ ] **Step 3: 在 `hai_agent/providers/base.py` 中集成速率限制器**

在 `BaseProvider.__init__` 中添加可选的 `rate_limiter` 参数：

```python
from .rate_limiter import TokenBucketRateLimiter, RateLimitConfig

class BaseProvider:
    def __init__(self, ..., rate_limiter: Optional[TokenBucketRateLimiter] = None):
        ...
        self._rate_limiter = rate_limiter

    def _apply_rate_limit(self, estimated_tokens: int = 0) -> None:
        """应用速率限制。"""
        if self._rate_limiter:
            self._rate_limiter.wait_and_acquire(estimated_tokens)
```

**注意**：具体修改位置需根据 base.py 实际构造函数调整。如果 base.py 的 `__init__` 不接受额外参数，则改用 setter 方法或通过 `Agent.__init__` 注入。

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_rate_limiter.py -v --tb=short`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hai_agent/providers/rate_limiter.py hai_agent/providers/base.py tests/test_rate_limiter.py
git commit -m "feat: 令牌桶速率限制器 — 控制 Provider 请求频率和 token 消耗"
```

---

## Task 7: 运行完整测试验证

- [ ] **Step 1: 运行所有单元测试**

Run: `pytest tests/ -v --tb=short -x --ignore=tests/test_integration_live.py --ignore=tests/test_integration_tools.py`
Expected: PASS

- [ ] **Step 2: 运行集成测试（如 Ollama 可用）**

Run: `python tests/test_integration_live.py`
Expected: 17/17 通过

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: 完成 P2 改进项 — MCP 连接池、指标系统、流式超时、速率限制

P2 改进项全部完成：
- MCP 连接池：后台事件循环 + 连接复用，避免每次调用启动新进程
- MetricsCollector：订阅事件系统聚合运行时指标
- PrometheusExporter：可选依赖导出器，未安装时自动降级
- 流式传输超时：空闲超时 + 总超时双重保护
- 令牌桶速率限制器：请求频率 + token 消耗双桶控制

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 验收标准

| 改进项 | 验收标准 |
|--------|----------|
| MCP 连接池 | 相同配置的 MCP 工具调用复用连接，不创建新进程 |
| MetricsCollector | 订阅事件后可获取 Provider/Tool/Session 指标快照 |
| PrometheusExporter | prometheus_client 可选依赖，未安装时降级为日志输出 |
| 流式超时 | 空闲 30s 或总时长 120s 后抛 StreamTimeoutError |
| 速率限制器 | 超过配置的 RPM/TPM 时自动等待或拒绝 |
| Agent 集成 | `agent.metrics` 属性可用，自动收集指标 |

---

## 后续改进 (P3)

不在本计划范围内，记录供参考：
- 数据库存储后端（Redis/PostgreSQL）
- 健康检查接口
- MemoryStore 文件写入加锁
- OpenTelemetry 集成（替代/补充 Prometheus）
- MCP 连接池监控指标
