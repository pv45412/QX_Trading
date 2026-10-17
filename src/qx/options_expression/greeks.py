"""Canonical semantic availability rules for option Greeks."""

from __future__ import annotations

import math
from typing import Any, Mapping


def is_greek_available(
    value: Any,
    provenance: Any,
    metadata: Mapping[str, Any] | None = None,
) -> bool:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(numeric_value):
        return False

    provenance_value = str(getattr(provenance, "value", provenance or "")).upper()
    if provenance_value in {"", "UNAVAILABLE"}:
        return False

    evidence = metadata or {}
    if evidence.get("combined") is True:
        return bool(
            evidence.get("all_legs_available") is True
            and evidence.get("source_metadata_valid") is True
        )
    if provenance_value == "MODEL_CALCULATED":
        if not evidence.get("pricing_model") or not evidence.get(
            "calculation_timestamp"
        ):
            return False
        for key in ("risk_free_rate", "dividend_yield", "volatility_input"):
            try:
                metadata_value = float(evidence.get(key))
            except (TypeError, ValueError):
                return False
            if not math.isfinite(metadata_value):
                return False
        if float(evidence["volatility_input"]) < 0:
            return False
    if provenance_value == "BROKER_PROVIDED" and evidence.get(
        "require_source_metadata", False
    ):
        return bool(evidence.get("broker_source") and evidence.get("quote_timestamp"))
    return provenance_value in {"BROKER_PROVIDED", "MODEL_CALCULATED"}
