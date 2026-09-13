"""Read-only onboarding audit; publisher identity does not certify cached data."""
from pathlib import Path
from typing import Any

from qx.data.membership import membership_provenance, membership_symbols, validate_membership_change

SOURCES = {
    "sp500": ("S&P Dow Jones Indices", "https://www.spglobal.com/spdji/en/landing/topic/api-data-solutions/"),
    "sp100": ("S&P Dow Jones Indices", "https://www.spglobal.com/spdji/en/landing/topic/api-data-solutions/"),
    "dow_jones": ("S&P Dow Jones Indices", "https://www.spglobal.com/spdji/en/landing/topic/api-data-solutions/"),
    "nasdaq_100": ("Nasdaq", "https://www.nasdaq.com/products/global-indexes/nasdaq-100/companies"),
    "russell_2000": ("FTSE Russell", "https://www.lseg.com/en/ftse-russell/index-resources/constituent-weights"),
}


def audit_membership(cache: Path, universe: str) -> dict[str, Any]:
    if universe not in SOURCES:
        raise ValueError("Unsupported universe")
    publisher, reference = SOURCES[universe]
    path = cache / f"{universe}_symbols.csv"
    report: dict[str, Any] = {
        "universe": universe, "publisher": publisher, "publisher_reference": reference,
        "official_verified": False, "structure_valid": False, "count": None,
        "provenance": membership_provenance(path),
        "missing_evidence": ["Authenticated publisher constituent artifact",
                             "Publisher effective date", "Complete constituent reconciliation"],
    }
    try:
        symbols = membership_symbols(path.read_bytes())
        report["count"] = len(symbols)
        validate_membership_change(universe, symbols, [])
        report["structure_valid"] = True
    except (OSError, ValueError):
        report["validation_error"] = "Missing or invalid cached membership"
    return report
