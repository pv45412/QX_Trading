"""Pure, zero-dependency price normalization and futures basis calculation module.

Independent of provider clients, broker adapters, yfinance, or pandas dataframes.
"""
from typing import Any


def calculate_es_spx_basis(price_es: float, price_spx: float) -> dict[str, Any]:
    """Calculate dynamic basis spread between /ES futures and SPX cash index.

    live_basis = price_es - price_spx
    """
    if price_es <= 0 or price_spx <= 0:
        return {"basis": 0.0, "is_valid": False, "price_es": price_es, "price_spx": price_spx}
    basis = round(price_es - price_spx, 2)
    return {
        "price_es": price_es,
        "price_spx": price_spx,
        "basis": basis,
        "is_valid": True,
    }


def normalize_es_target_to_spx(target_es: float, basis: float) -> float:
    """Convert an /ES technical target or trigger level into SPX cash equivalent.
    
    Formula: target_spx_cash = target_es - basis (since /ES trades at a premium to cash SPX).
    """
    return round(target_es - basis, 2)
