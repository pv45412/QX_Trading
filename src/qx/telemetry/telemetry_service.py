"""Backward compatibility layer re-exporting Telemetry & Signal Audit Logging Service.

Canonical domain package: qx.telemetry
"""

from qx.telemetry import SignalTelemetryRecord, TelemetryService

__all__ = [
    "SignalTelemetryRecord",
    "TelemetryService",
]
