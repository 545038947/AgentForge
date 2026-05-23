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

    def test_on_provider_response_dict(self):
        collector = MetricsCollector()
        collector.on_provider_response({
            "provider_name": "ollama",
            "latency_ms": 100.0,
            "is_error": False,
            "error_type": None,
            "usage": None,
        })
        snapshot = collector.get_snapshot()
        assert snapshot["providers"]["ollama"]["total_requests"] == 1


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
