"""Canonical research_v1 sector taxonomy and provider normalization."""

from __future__ import annotations

from dataclasses import dataclass
import re


SECTOR_MAPPING_SOURCE = "qx_canonical_sector_taxonomy"
SECTOR_MAPPING_VERSION = "research_v1"

CANONICAL_SECTOR_IDS = frozenset(
    {"XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"}
)

_ALIASES = {
    # Technology
    "XLK": "XLK",
    "TECH": "XLK",
    "TECHNOLOGY": "XLK",
    "INFORMATION TECHNOLOGY": "XLK",
    "SEMICONDUCTORS": "XLK",
    # Financials
    "XLF": "XLF",
    "FINANCIAL": "XLF",
    "FINANCIALS": "XLF",
    "FINANCIAL SERVICES": "XLF",
    # Energy
    "XLE": "XLE",
    "ENERGY": "XLE",
    # Health Care
    "XLV": "XLV",
    "HEALTH CARE": "XLV",
    "HEALTHCARE": "XLV",
    "HEALTH CARE EQUIPMENT": "XLV",
    "BIOTECHNOLOGY": "XLV",
    "PHARMACEUTICALS": "XLV",
    # Consumer Discretionary
    "XLY": "XLY",
    "CONSUMER DISCRETIONARY": "XLY",
    # Consumer Staples
    "XLP": "XLP",
    "CONSUMER STAPLES": "XLP",
    # Industrials
    "XLI": "XLI",
    "INDUSTRIAL": "XLI",
    "INDUSTRIALS": "XLI",
    # Materials
    "XLB": "XLB",
    "MATERIAL": "XLB",
    "MATERIALS": "XLB",
    # Utilities
    "XLU": "XLU",
    "UTILITIES": "XLU",
    "UTILITY": "XLU",
    # Real Estate
    "XLRE": "XLRE",
    "REAL ESTATE": "XLRE",
    # Communication Services
    "XLC": "XLC",
    "COMMUNICATION SERVICES": "XLC",
    "COMMUNICATION SERVICE": "XLC",
    "MEDIA & ENTERTAINMENT": "XLC",
    "MEDIA AND ENTERTAINMENT": "XLC",
    "TELECOMMUNICATION SERVICES": "XLC",
    "TELECOM": "XLC",
}


# ---------------------------------------------------------------------------
# Leveraged / Inverse ETF ticker → (canonical_sector_id, human_label)
# These ETFs don't carry a standard GICS sector from brokers or yfinance;
# we hardcode their underlying sector exposure here.
# ---------------------------------------------------------------------------
_LEVERAGED_ETF_MAP: dict[str, tuple[str, str]] = {
    # Technology / Semiconductors (XLK)
    "SOXL": ("XLK", "3X Semiconductors"),
    "SOXS": ("XLK", "3X Inv Semiconductors"),
    "TECL": ("XLK", "3X Technology"),
    "TECS": ("XLK", "3X Inv Technology"),
    "TQQQ": ("XLK", "3X Nasdaq-100"),
    "SQQQ": ("XLK", "3X Inv Nasdaq-100"),
    "QLD":  ("XLK", "2X Nasdaq-100"),
    "QID":  ("XLK", "2X Inv Nasdaq-100"),
    "ROM":  ("XLK", "2X Technology"),
    "REW":  ("XLK", "2X Inv Technology"),
    # Financials (XLF)
    "FAS":  ("XLF", "3X Financials"),
    "FAZ":  ("XLF", "3X Inv Financials"),
    "UYG":  ("XLF", "2X Financials"),
    "SKF":  ("XLF", "2X Inv Financials"),
    # Energy (XLE)
    "ERX":  ("XLE", "2X Energy"),
    "ERY":  ("XLE", "2X Inv Energy"),
    "GUSH": ("XLE", "2X Oil & Gas"),
    "DRIP": ("XLE", "2X Inv Oil & Gas"),
    # Health Care / Biotech (XLV)
    "LABU": ("XLV", "3X Biotech"),
    "LABD": ("XLV", "3X Inv Biotech"),
    "BIB":  ("XLV", "2X Biotech"),
    "BIS":  ("XLV", "2X Inv Biotech"),
    # Materials / Miners (XLB)
    "NUGT": ("XLB", "2X Gold Miners"),
    "DUST": ("XLB", "2X Inv Gold Miners"),
    "JNUG": ("XLB", "3X Junior Gold Miners"),
    "JDST": ("XLB", "3X Inv Junior Gold Miners"),
    # Industrials (XLI)
    "WANT": ("XLI", "3X Industrials"),
    # Consumer Discretionary (XLY)
    "CURE": ("XLY", "3X Consumer Discretionary"),
    # Utilities (XLU)
    "UTSL": ("XLU", "3X Utilities"),
    # Real Estate (XLRE)
    "DRN":  ("XLRE", "3X Real Estate"),
    "DRV":  ("XLRE", "3X Inv Real Estate"),
}


@dataclass(frozen=True)
class SectorMapping:
    provider_sector_raw: str | None
    canonical_sector_id: str | None
    sector_status: str
    sector_mapping_source: str = SECTOR_MAPPING_SOURCE
    sector_mapping_version: str = SECTOR_MAPPING_VERSION


def normalize_sector(value: object) -> SectorMapping:
    raw = value.strip() if isinstance(value, str) else None
    normalized = re.sub(r"[\s_-]+", " ", raw.upper()).strip() if raw else ""
    canonical = _ALIASES.get(normalized)
    return SectorMapping(
        provider_sector_raw=raw or None,
        canonical_sector_id=canonical,
        sector_status="KNOWN" if canonical is not None else "UNKNOWN",
    )


def normalize_sector_by_ticker(ticker: str) -> SectorMapping | None:
    """Return a SectorMapping for known leveraged/inverse ETF tickers.

    Returns None if the ticker is not in the leveraged ETF map.
    """
    key = ticker.strip().upper()
    entry = _LEVERAGED_ETF_MAP.get(key)
    if entry is None:
        return None
    canonical_id, label = entry
    return SectorMapping(
        provider_sector_raw=label,
        canonical_sector_id=canonical_id,
        sector_status="KNOWN",
    )
