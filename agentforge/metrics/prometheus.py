"""Prometheus 指标导出器 — 将 MetricsCollector 快照暴露为 Prometheus 指标。

依赖：prometheus_client（可选，未安装时自动降级为日志输出）。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        Counter, Histogram, Gauge,
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
            logger.debug(f"指标快照（Prometheus 未安装）: providers={len(snapshot.get('providers', {}))}")
            return

        for name, pm in snapshot.get("providers", {}).items():
            reqs = pm.get("total_requests", 0)
            if reqs > 0:
                self._provider_requests.labels(provider=name).inc(reqs)
            errors = pm.get("total_errors", 0)
            if errors > 0:
                self._provider_errors.labels(provider=name, error_type="all").inc(errors)
            for etype, count in pm.get("by_error_type", {}).items():
                if count > 0:
                    self._provider_errors.labels(provider=name, error_type=etype).inc(count)
            latency = pm.get("avg_latency_ms", 0.0)
            if latency > 0 and reqs > 0:
                self._provider_latency.labels(provider=name).observe(latency)
            tokens_in = pm.get("total_tokens_in", 0)
            if tokens_in > 0:
                self._provider_tokens_in.labels(provider=name).inc(tokens_in)
            tokens_out = pm.get("total_tokens_out", 0)
            if tokens_out > 0:
                self._provider_tokens_out.labels(provider=name).inc(tokens_out)

        for name, tm in snapshot.get("tools", {}).items():
            calls = tm.get("total_calls", 0)
            if calls > 0:
                self._tool_calls.labels(tool=name).inc(calls)
            errors = tm.get("total_errors", 0)
            if errors > 0:
                self._tool_errors.labels(tool=name).inc(errors)
            latency = tm.get("avg_latency_ms", 0.0)
            if latency > 0 and calls > 0:
                self._tool_latency.labels(tool=name).observe(latency)

        sm = snapshot.get("session", {})
        turns = sm.get("total_turns", 0)
        if turns > 0:
            self._session_turns.inc(turns)
        tokens_in = sm.get("total_tokens_in", 0)
        if tokens_in > 0:
            self._session_tokens_in.inc(tokens_in)
        tokens_out = sm.get("total_tokens_out", 0)
        if tokens_out > 0:
            self._session_tokens_out.inc(tokens_out)

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
        """获取 Prometheus 文本格式指标。"""
        if not _PROMETHEUS_AVAILABLE:
            return "# prometheus_client 未安装\n"
        return generate_latest(self._registry).decode("utf-8")
