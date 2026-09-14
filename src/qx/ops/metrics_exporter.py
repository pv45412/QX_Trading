"""Prometheus-formatted operational metrics generator."""

import os
import time


class MetricsExporter:
    """Generates Prometheus plain text metrics for system monitoring scrapers."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._start_time = time.time()

    def increment_counter(self, name: str, value: float = 1.0) -> None:
        """Increment a counter metric."""
        self._counters[name] = self._counters.get(name, 0.0) + value

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge metric value."""
        self._gauges[name] = value

    def export_prometheus_metrics(self) -> str:
        """Render Prometheus exposition text format."""
        lines = [
            "# HELP qx_uptime_seconds Total runtime of QX backend process",
            "# TYPE qx_uptime_seconds counter",
            f"qx_uptime_seconds {time.time() - self._start_time:.2f}",
        ]

        for name, value in self._counters.items():
            clean_name = f"qx_{name.lower()}"
            lines.append(f"# HELP {clean_name} QX operational counter")
            lines.append(f"# TYPE {clean_name} counter")
            lines.append(f"{clean_name} {value}")

        for name, value in self._gauges.items():
            clean_name = f"qx_{name.lower()}"
            lines.append(f"# HELP {clean_name} QX operational gauge")
            lines.append(f"# TYPE {clean_name} gauge")
            lines.append(f"{clean_name} {value}")

        return "\n".join(lines) + "\n"
