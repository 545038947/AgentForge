"""Prometheus 导出器测试。"""

from unittest.mock import MagicMock

from agentforge.metrics.prometheus import PrometheusExporter, _PROMETHEUS_AVAILABLE


class TestPrometheusExporterNoLib:
    """prometheus_client 未安装时的降级行为。"""

    def test_export_without_lib(self):
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

    def test_start_http_server_without_lib(self):
        exporter = PrometheusExporter(port=9090)
        exporter.start_http_server()  # 不应抛异常


class TestPrometheusExporterWithLib:
    """prometheus_client 已安装时的行为。"""

    def test_export_updates_counters(self):
        if not _PROMETHEUS_AVAILABLE:
            return  # 跳过

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

    def test_export_empty_snapshot(self):
        if not _PROMETHEUS_AVAILABLE:
            return
        exporter = PrometheusExporter()
        exporter.export({"providers": {}, "tools": {}, "session": {"total_turns": 0}})