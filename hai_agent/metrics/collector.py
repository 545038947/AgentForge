"""指标收集中间层 — 订阅事件系统，聚合运行时指标。"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
        collector.bind(event_dispatcher)

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

    def bind(self, event_dispatcher: Any) -> None:
        """绑定到事件分发器，订阅事件更新指标。"""
        from hai_agent.events import EventType
        event_dispatcher.on(EventType.PROVIDER_RESPONSE, self._on_provider_response)
        event_dispatcher.on(EventType.PROVIDER_ERROR, self._on_provider_error)
        event_dispatcher.on(EventType.TOOL_END, self._on_tool_end)
        event_dispatcher.on(EventType.AGENT_END, self._on_agent_end)

    def on_provider_response(self, event: Any) -> None:
        """处理 Provider 响应事件。"""
        provider_name = _extract(event, "provider_name", "unknown")
        usage = _extract(event, "usage", None)
        latency_ms = _extract(event, "latency_ms", 0.0)
        is_error = _extract(event, "is_error", False)
        error_type = _extract(event, "error_type", None)

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
        provider_name = _extract(event, "provider_name", "unknown")
        error_type = _extract(event, "error_type", "unknown")
        latency_ms = _extract(event, "latency_ms", 0.0)

        with self._lock:
            pm = self._providers[provider_name]
            pm.total_requests += 1
            pm.total_errors += 1
            pm.total_latency_ms += latency_ms
            pm.last_request_ts = time.monotonic()
            pm.by_error_type[error_type] += 1

    def on_tool_end(self, event: Any) -> None:
        """处理工具执行结束事件。"""
        tool_name = _extract(event, "tool_name", "unknown")
        latency_ms = _extract(event, "latency_ms", 0.0)
        is_error = _extract(event, "is_error", False)

        with self._lock:
            tm = self._tools[tool_name]
            tm.total_calls += 1
            tm.total_latency_ms += latency_ms
            tm.last_call_ts = time.monotonic()
            if is_error:
                tm.total_errors += 1

    def _on_provider_response(self, event: Any) -> None:
        """内部事件回调（Event 对象）。"""
        data = getattr(event, "data", None) or {}
        provider_name = data.get("provider_name", "unknown")
        response = data.get("response")
        is_error = False
        latency_ms = 0.0
        usage = None
        if response:
            latency_ms = getattr(response, "latency_ms", 0.0)
            usage = getattr(response, "usage", None)
            if getattr(response, "finish_reason", "") == "error":
                is_error = True
        self.on_provider_response(_make_event_dict(
            provider_name=provider_name, latency_ms=latency_ms,
            is_error=is_error, usage=usage
        ))

    def _on_provider_error(self, event: Any) -> None:
        """内部事件回调（Event 对象）。"""
        data = getattr(event, "data", None) or {}
        error = data.get("error")
        error_type = "unknown"
        if error:
            error_type = type(error).__name__
        self.on_provider_error(_make_event_dict(
            provider_name=data.get("provider_name", "unknown"),
            error_type=error_type
        ))

    def _on_tool_end(self, event: Any) -> None:
        """内部事件回调（Event 对象）。"""
        data = getattr(event, "data", None) or {}
        tool_name = data.get("tool_name", "unknown")
        is_error = data.get("is_error", False)
        latency_ms = data.get("latency_ms", 0.0)
        self.on_tool_end(_make_event_dict(
            tool_name=tool_name, latency_ms=latency_ms, is_error=is_error
        ))

    def _on_agent_end(self, event: Any) -> None:
        """内部事件回调（Agent 结束 = 会话轮次结束）。"""
        with self._lock:
            self._session.total_turns += 1

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


def _extract(obj: Any, attr: str, default: Any) -> Any:
    """从对象或字典中提取属性。"""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _make_event_dict(**kwargs) -> dict:
    """创建事件字典（用于统一处理 Event 对象和普通字典）。"""
    return kwargs