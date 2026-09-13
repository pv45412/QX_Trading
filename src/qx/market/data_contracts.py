"""Declared evidence contracts for market-workspace facets.

The registry is intentionally independent of a UI or vendor client.  A screen can
ask what it is allowed to show from the artifacts it has, rather than treating a
cache file or a successful HTTP response as sufficient evidence for every claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SourceContract:
    key: str
    label: str
    access: str
    url: str
    notes: str


@dataclass(frozen=True)
class FacetContract:
    key: str
    label: str
    required_artifacts: tuple[str, ...]
    source_keys: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class FacetReadiness:
    key: str
    label: str
    status: str
    missing_artifacts: tuple[str, ...]
    source_keys: tuple[str, ...]
    limitations: tuple[str, ...]


SOURCES: tuple[SourceContract, ...] = (
    SourceContract(
        "schwab_market_data", "Schwab market data", "authenticated broker API",
        "https://developer.schwab.com/", "Quotes, price history and option-chain fields; every response needs symbol and freshness validation.",
    ),
    SourceContract(
        "bls_calendar", "BLS release calendar", "public", "https://www.bls.gov/schedule/news_release/bls.ics",
        "Scheduled BLS releases only. It does not provide a consensus estimate, surprise, or trade direction.",
    ),
    SourceContract(
        "fomc_calendar", "Federal Reserve FOMC calendar", "public", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "Meeting schedule and policy-event timing; dates remain tentative until confirmed by the Committee.",
    ),
    SourceContract(
        "treasury_calendar", "Treasury auction calendar", "public", "https://treasurydirect.services.treasury.gov/auctions/announcements-data-results/",
        "Auction schedules and results. The schedule can change and must be refreshed from the publisher.",
    ),
    SourceContract(
        "cme_contract_specs", "CME contract specifications", "public", "https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.contractSpecs.html",
        "Product and roll reference only; not a live market-data feed.",
    ),
    SourceContract(
        "occ_open_interest", "OCC volume and open interest", "public delayed aggregate reports", "https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/volume-query",
        "Daily aggregate data. It is not real-time order flow, customer positioning, or dealer gamma.",
    ),
)


FACETS: tuple[FacetContract, ...] = (
    FacetContract(
        "futures_context", "ES / NQ market context",
        ("fresh_futures_quote", "explicit_contract_history", "continuous_mapping", "cash_session_alignment"),
        ("schwab_market_data", "cme_contract_specs"),
        ("A completed daily series is not an intraday trade signal.",),
    ),
    FacetContract(
        "intraday_structure", "Five-minute intraday structure",
        ("fresh_futures_quote", "five_minute_bars", "explicit_contract_history", "cash_session_alignment"),
        ("schwab_market_data", "cme_contract_specs"),
        ("Levels are withheld when quote, bar, contract, or cash-session clocks do not align.",),
    ),
    FacetContract(
        "event_risk", "Scheduled event risk",
        ("bls_schedule", "fomc_schedule", "retrieval_timestamp"),
        ("bls_calendar", "fomc_calendar", "treasury_calendar"),
        ("Schedules identify timing only; they do not predict price direction or quantify surprise risk.",),
    ),
    FacetContract(
        "spx_options_surface", "SPX option-chain surface",
        ("option_chain_timestamp", "valid_bid_ask", "expiration_identity", "open_interest_timestamp"),
        ("schwab_market_data", "occ_open_interest"),
        ("Open interest can be delayed and does not identify who holds risk.",),
    ),
    FacetContract(
        "gamma_proxy", "Open-interest concentration proxy",
        ("option_chain_timestamp", "valid_bid_ask", "open_interest_timestamp", "iv_timestamp", "calculation_version"),
        ("schwab_market_data", "occ_open_interest"),
        ("This may show concentration only. It must never be labelled dealer gamma exposure without a validated model and position-sign assumptions.",),
    ),
    FacetContract(
        "options_flow", "Options flow", ("licensed_realtime_flow", "flow_methodology", "flow_timestamp"), (),
        ("No free public source establishes real-time sweep, customer-side, or dealer-side flow. Keep unavailable until licensed evidence is connected.",),
    ),
    FacetContract(
        "earnings_risk", "Earnings risk", ("issuer_or_licensed_earnings_calendar", "retrieval_timestamp"), (),
        ("A central free calendar is not treated as authoritative. Use issuer relations or a licensed calendar and retain source provenance.",),
    ),
    FacetContract(
        "outcome_tracking", "Reconciled outcome tracking", ("broker_fill_export", "cost_model_version", "strategy_version", "evaluation_window"), (),
        ("No performance metric is shown as live or predictive until fills, fees, slippage assumptions, and holdout window are recorded.",),
    ),
)


def assess_facets(artifacts: Mapping[str, bool]) -> tuple[FacetReadiness, ...]:
    """Return deterministic readiness without fetching data or promoting a signal."""
    results: list[FacetReadiness] = []
    for facet in FACETS:
        missing = tuple(key for key in facet.required_artifacts if artifacts.get(key) is not True)
        results.append(FacetReadiness(
            key=facet.key,
            label=facet.label,
            status="ready" if not missing else "blocked",
            missing_artifacts=missing,
            source_keys=facet.source_keys,
            limitations=facet.limitations,
        ))
    return tuple(results)


def source_contract(key: str) -> SourceContract:
    for source in SOURCES:
        if source.key == key:
            return source
    raise KeyError(f"Unknown data source: {key}")
