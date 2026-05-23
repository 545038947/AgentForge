# Metrics API

## MetricsCollector

::: hai_agent.metrics.collector.MetricsCollector
    options:
      show_source: false
      members:
        - bind
        - get_snapshot
        - reset
        - export

## PrometheusExporter

::: hai_agent.metrics.prometheus.PrometheusExporter
    options:
      show_source: false
      members:
        - export
        - start_http_server
        - get_metrics_text

## ProviderMetrics

::: hai_agent.metrics.collector.ProviderMetrics
    options:
      show_source: false

## ToolMetrics

::: hai_agent.metrics.collector.ToolMetrics
    options:
      show_source: false

## SessionMetrics

::: hai_agent.metrics.collector.SessionMetrics
    options:
      show_source: false
