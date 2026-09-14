"""Unit tests for QX Production Operations, Health Monitoring & Metrics Engine."""

from qx.ops import AlertDispatcher, HealthChecker, MetricsExporter, SystemHealthReport


def test_health_checker_audit():
    """Verify health auditor returns valid SystemHealthReport."""
    checker = HealthChecker()
    report = checker.audit_system_health()

    assert isinstance(report, SystemHealthReport)
    assert report.status in {"OK", "DEGRADED", "ERROR"}
    assert len(report.components) >= 1


def test_prometheus_metrics_exporter():
    """Verify Prometheus exposition text output."""
    exporter = MetricsExporter()
    exporter.increment_counter("api_requests_total", 5.0)
    exporter.set_gauge("active_connections", 2.0)

    text = exporter.export_prometheus_metrics()
    assert "qx_uptime_seconds" in text
    assert "qx_api_requests_total 5.0" in text
    assert "qx_active_connections 2.0" in text


def test_alert_webhook_dispatcher():
    """Verify alert payload generation and history tracking."""
    dispatcher = AlertDispatcher()
    alert = dispatcher.dispatch_alert("WARNING", "order_router", "Adverse slippage detected", {"slippage_bps": 45.0})

    assert alert.level == "WARNING"
    assert alert.source == "order_router"
    assert alert.metadata["slippage_bps"] == 45.0
    assert len(dispatcher.get_history()) == 1
