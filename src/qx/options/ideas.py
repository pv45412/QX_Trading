from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, TypeVar

import pandas as pd

from qx.models.scan import ScanCandidate
from qx.options.chains import OptionContract, OptionsChainProvider
from qx.data.fundamentals import FundamentalProvider
from qx.options.quality import FundamentalSnapshot
from qx.options.quality import UnderlyingQualityProfile, evaluate_underlying_quality
from qx.options.strategy_selection import select_directional_strategy
from qx.options.timing import EmaTimingProvider, EmaTimingSnapshot
from qx.patterns.ranking import composite_rank_score, sort_candidates
from qx.watchlist.engine import WatchlistCandidate

T = TypeVar("T")

__all__ = [
    "OptionIdea",
    "OptionTradePlan",
    "build_option_trade_plan",
    "evaluate_underlying_quality",
    "generate_directional_option_ideas",
    "generate_option_ideas",
    "option_ideas_frame",
]


@dataclass(frozen=True)
class OptionIdea:
    symbol: str
    direction: str
    bucket: str
    strategy: str
    action: str
    score: float
    idea_score: float
    contract_score: float
    liquidity_score: float
    setup_quality: str
    liquidity_note: str
    volatility_note: str
    risk_note: str
    rationale: str
    regime_bucket: str = ""
    strategy_reason: str = ""
    exit_plan: str = ""
    underlying_quality_score: float = 0.0
    underlying_quality: str = "Not evaluated"
    income_suitability: str = "Not evaluated"
    leaps_suitability: str = "Not evaluated"
    quality_gate: str = "Not evaluated"
    technical_timing: str = "Daily setup only"
    fundamental_note: str = ""
    quality_breakdown: str = ""
    quality_missing: str = ""
    market_cap: float = 0.0
    eps_growth: float = 0.0
    revenue_growth: float = 0.0
    roe: float = 0.0
    debt_to_equity: float = 0.0
    profit_margin: float = 0.0
    free_cash_flow_positive: bool = False
    timing_score: float = 0.0
    timing_label: str = "Not checked"
    timing_trigger: str = "Not checked"
    ema_alignment: str = ""
    source: str = "Rectangle"
    underlying_score: float = 0.0
    directional_score: float = 0.0
    options_bias: str = ""
    setup_type: str = ""
    underlying_price: float = 0.0
    contract_symbol: str = ""
    expiration: str = ""
    strike: float = 0.0
    dte: int = 0
    bid: float = 0.0
    ask: float = 0.0
    open_interest: int = 0
    volume: int = 0
    implied_volatility: float = 0.0
    spread_pct: float = 0.0


@dataclass(frozen=True)
class OptionTradePlan:
    symbol: str
    title: str
    thesis: str
    structure: str
    entry_checklist: list[str]
    invalidation: str
    target: str
    risk_controls: list[str]
    next_action: str


def generate_option_ideas(
    candidates: list[ScanCandidate],
    *,
    limit: int = 25,
    chain_provider: OptionsChainProvider | None = None,
) -> list[OptionIdea]:
    eligible = [
        candidate
        for candidate in sort_candidates(candidates)
        if candidate.setup_score >= 0.60 and candidate.setup_status != "Invalidated"
    ]
    selected = eligible[:limit]

    def build_idea(candidate: ScanCandidate) -> OptionIdea:
        contract = _best_contract(candidate, chain_provider) if chain_provider else None
        return _idea_from_candidate(candidate, contract)

    return _parallel_ordered(selected, build_idea, max_workers=8)


def generate_directional_option_ideas(
    candidates: list[WatchlistCandidate],
    *,
    limit: int = 25,
    min_directional_score: float = 0.50,
    chain_provider: OptionsChainProvider | None = None,
    fundamental_provider: FundamentalProvider | None = None,
    timing_provider: EmaTimingProvider | None = None,
) -> list[OptionIdea]:
    eligible = [
        candidate
        for candidate in sorted(
            candidates,
            key=lambda item: (item.readiness_score, item.directional_score, item.final_score),
            reverse=True,
        )
        if candidate.directional_score >= min_directional_score and candidate.options_bias != "Neutral"
    ]
    selected = eligible[:limit]

    def build_idea(candidate: WatchlistCandidate) -> OptionIdea:
        contract = _best_directional_contract(candidate, chain_provider) if chain_provider else None
        fundamentals = _safe_fundamentals(candidate.symbol, fundamental_provider)
        timing = _safe_timing(candidate.symbol, timing_provider)
        return _idea_from_watchlist_candidate(candidate, contract, fundamentals, timing)

    return _parallel_ordered(selected, build_idea, max_workers=8)


def option_ideas_frame(ideas: list[OptionIdea]) -> pd.DataFrame:
    return pd.DataFrame([idea.__dict__ for idea in ideas])


def _parallel_ordered(
    items: list[T],
    build_item: Callable[[T], OptionIdea],
    *,
    max_workers: int,
) -> list[OptionIdea]:
    if not items:
        return []
    results: list[OptionIdea | None] = [None] * len(items)
    workers = max(1, min(max_workers, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_by_index = {executor.submit(build_item, item): index for index, item in enumerate(items)}
        for future in as_completed(future_by_index):
            results[future_by_index[future]] = future.result()
    return [result for result in results if result is not None]


def build_option_trade_plan(idea: OptionIdea) -> OptionTradePlan:
    direction_text = "upside" if idea.direction == "Bullish" else "downside"
    contract_text = (
        f"{idea.contract_symbol} expiring {idea.expiration}"
        if idea.contract_symbol
        else "No validated contract attached yet"
    )
    entry_checklist = [
        f"Underlying quality gate is {idea.quality_gate}: {idea.underlying_quality}.",
        f"Regime strategy bucket: {idea.regime_bucket or 'not classified'}.",
        f"Strategy reason: {idea.strategy_reason or 'not available'}.",
        f"Quality breakdown: {idea.quality_breakdown or 'not available'}.",
        idea.technical_timing,
        f"Underlying confirms {direction_text} trigger from {idea.setup_type or idea.strategy}.",
        "Bid/ask spread remains acceptable before entry.",
        "No major earnings or event risk before planned exit.",
    ]
    if idea.action != "Trade Candidate":
        entry_checklist.append("Wait for action bucket to improve before treating as executable.")

    invalidation = (
        "Invalidate if underlying loses setup support or directional score deteriorates."
        if idea.direction == "Bullish"
        else "Invalidate if underlying reclaims resistance or bearish momentum fades."
    )
    if idea.exit_plan:
        target = idea.exit_plan
    elif idea.direction == "Bullish":
        target = "First target is resistance breakout follow-through; trim into fast premium expansion."
    else:
        target = "First target is downside continuation; trim into volatility expansion."
    return OptionTradePlan(
        symbol=idea.symbol,
        title=f"{idea.symbol} {idea.direction} {idea.strategy}",
        thesis=idea.rationale,
        structure=f"{idea.strategy}; preferred contract: {contract_text}; DTE bucket: {idea.bucket}.",
        entry_checklist=entry_checklist,
        invalidation=invalidation,
        target=target,
        risk_controls=[
            note
            for note in [
                idea.risk_note,
                idea.liquidity_note,
                idea.volatility_note,
                idea.fundamental_note,
                f"Missing checks: {idea.quality_missing}" if idea.quality_missing else "",
                "Use defined risk; do not size from conviction alone.",
            ]
            if note
        ],
        next_action=idea.action,
    )


def _idea_from_candidate(
    candidate: ScanCandidate,
    contract: OptionContract | None = None,
) -> OptionIdea:
    distance = candidate.metrics.resistance_distance_pct
    relative_volume = candidate.metrics.relative_volume_20d
    direction = "Bullish"
    rank_score = composite_rank_score(candidate)
    contract_score = _contract_score(contract, candidate.metrics.resistance) if contract else 0.0
    liquidity_score = _liquidity_score(contract) if contract else _liquidity_proxy(candidate)
    idea_score = _idea_score(candidate, contract_score, liquidity_score)

    if candidate.setup_status == "Breakout":
        bucket = "30-60 DTE"
        strategy = "Call debit spread"
    elif distance <= 0.05:
        bucket = "45-90 DTE"
        strategy = "Long call or call debit spread"
    else:
        bucket = "60-120 DTE"
        strategy = "Watchlist only or bull put spread after confirmation"

    action = _action_label(idea_score, candidate, contract)

    liquidity_note = (
        _contract_liquidity_note(contract)
        if contract
        else (
            "Better stock volume confirmation"
            if relative_volume >= 1.0
            else "Wait for volume confirmation"
        )
    )
    volatility_note = (
        "Compression favors defined-risk premium buying"
        if candidate.metrics.atr_ratio_5_to_20 <= 0.80
        else "Volatility not compressed; avoid overpaying"
    )
    risk_note = _risk_note(candidate, contract)
    rationale = (
        f"{candidate.setup_status}; rank {rank_score:.2f}; "
        f"{distance:.1%} from resistance."
    )
    return OptionIdea(
        symbol=candidate.symbol,
        direction=direction,
        bucket=bucket,
        strategy=strategy,
        action=action,
        score=round(rank_score, 3),
        idea_score=round(idea_score, 3),
        contract_score=round(contract_score, 3),
        liquidity_score=round(liquidity_score, 3),
        setup_quality=candidate.quality_label,
        liquidity_note=liquidity_note,
        volatility_note=volatility_note,
        risk_note=risk_note,
        rationale=rationale,
        source="Rectangle",
        underlying_score=round(rank_score, 3),
        directional_score=0.0,
        options_bias=direction,
        setup_type=candidate.setup_status,
        underlying_price=round(
            candidate.metrics.resistance * (1 - candidate.metrics.resistance_distance_pct),
            2,
        ),
        contract_symbol=contract.contract_symbol if contract else "",
        expiration=contract.expiration.isoformat() if contract else "",
        strike=round(contract.strike, 2) if contract else 0.0,
        dte=contract.dte if contract else 0,
        bid=round(contract.bid, 2) if contract else 0.0,
        ask=round(contract.ask, 2) if contract else 0.0,
        open_interest=contract.open_interest if contract else 0,
        volume=contract.volume if contract else 0,
        implied_volatility=round(contract.implied_volatility, 4) if contract else 0.0,
        spread_pct=round(contract.spread_pct, 4) if contract else 0.0,
    )


def _idea_from_watchlist_candidate(
    candidate: WatchlistCandidate,
    contract: OptionContract | None = None,
    fundamentals: FundamentalSnapshot | None = None,
    timing: EmaTimingSnapshot | None = None,
) -> OptionIdea:
    direction = candidate.options_bias
    quality = evaluate_underlying_quality(candidate, fundamentals=fundamentals)
    strategy_selection = select_directional_strategy(candidate, quality, contract=contract, timing=timing)
    strategy = strategy_selection.instrument
    bucket = _directional_bucket(candidate, contract)
    contract_score = _contract_score(contract, candidate.close) if contract else 0.0
    liquidity_score = _liquidity_score(contract) if contract else max(0.0, min(candidate.relative_volume_20d / 1.5, 1.0))
    timing_score = timing.score if timing else 0.0
    idea_score = _directional_idea_score(candidate, contract_score, liquidity_score, quality.score, timing_score)
    action = _directional_action_label(idea_score, candidate, contract, quality, timing)
    rationale = (
        f"{candidate.readiness_label} / {candidate.setup_state}; "
        f"{candidate.options_setup}; {candidate.options_bias.lower()} bias; "
        f"quality {quality.score:.2f}; directional {candidate.directional_score:.2f}; "
        f"readiness {candidate.readiness_score:.2f}."
    )
    return OptionIdea(
        symbol=candidate.symbol,
        direction=direction,
        bucket=bucket,
        strategy=strategy,
        action=action,
        score=round(candidate.readiness_score, 3),
        idea_score=round(idea_score, 3),
        contract_score=round(contract_score, 3),
        liquidity_score=round(liquidity_score, 3),
        setup_quality=_directional_quality(candidate.directional_score),
        liquidity_note=(
            _contract_liquidity_note(contract)
            if contract
            else ("RVOL confirmed" if candidate.relative_volume_20d >= 1.2 else "Needs RVOL confirmation")
        ),
        volatility_note="IV rank pending; verify option pricing before entry",
        risk_note=_directional_risk_note(candidate, contract),
        rationale=rationale,
        regime_bucket=strategy_selection.regime_bucket,
        strategy_reason=strategy_selection.rationale,
        exit_plan=strategy_selection.exit_plan,
        underlying_quality_score=quality.score,
        underlying_quality=quality.label,
        income_suitability=quality.income_suitability,
        leaps_suitability=quality.leaps_suitability,
        quality_gate=quality.gate,
        technical_timing=quality.timing,
        fundamental_note=quality.fundamental_note,
        quality_breakdown=quality.breakdown,
        quality_missing=", ".join(quality.missing),
        market_cap=_snapshot_number(fundamentals.market_cap if fundamentals else None),
        eps_growth=_snapshot_number(fundamentals.eps_growth if fundamentals else None),
        revenue_growth=_snapshot_number(fundamentals.revenue_growth if fundamentals else None),
        roe=_snapshot_number(fundamentals.roe if fundamentals else None),
        debt_to_equity=_snapshot_number(fundamentals.debt_to_equity if fundamentals else None),
        profit_margin=_snapshot_number(fundamentals.profit_margin if fundamentals else None),
        free_cash_flow_positive=bool(fundamentals.free_cash_flow_positive) if fundamentals else False,
        timing_score=round(timing.score, 3) if timing else 0.0,
        timing_label=timing.label if timing else "Not checked",
        timing_trigger=timing.trigger if timing else "Not checked",
        ema_alignment=timing.alignment if timing else "",
        source="Broad Directional",
        underlying_score=round(candidate.readiness_score, 3),
        directional_score=candidate.directional_score,
        options_bias=candidate.options_bias,
        setup_type=candidate.options_setup,
        underlying_price=round(candidate.close, 2),
        contract_symbol=contract.contract_symbol if contract else "",
        expiration=contract.expiration.isoformat() if contract else "",
        strike=round(contract.strike, 2) if contract else 0.0,
        dte=contract.dte if contract else 0,
        bid=round(contract.bid, 2) if contract else 0.0,
        ask=round(contract.ask, 2) if contract else 0.0,
        open_interest=contract.open_interest if contract else 0,
        volume=contract.volume if contract else 0,
        implied_volatility=round(contract.implied_volatility, 4) if contract else 0.0,
        spread_pct=round(contract.spread_pct, 4) if contract else 0.0,
    )


def _best_contract(
    candidate: ScanCandidate,
    chain_provider: OptionsChainProvider | None,
) -> OptionContract | None:
    if chain_provider is None:
        return None
    try:
        contracts = chain_provider.get_calls(candidate.symbol)
    except Exception:
        return None

    close_proxy = candidate.metrics.resistance
    eligible = [
        contract
        for contract in contracts
        if 30 <= contract.dte <= 180
        and contract.open_interest >= 100
        and contract.volume >= 10
        and contract.spread_pct <= 0.25
        and contract.strike >= close_proxy * 0.95
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda contract: (_contract_score(contract, close_proxy)), reverse=True)
    return eligible[0]


def _best_directional_contract(
    candidate: WatchlistCandidate,
    chain_provider: OptionsChainProvider | None,
) -> OptionContract | None:
    if chain_provider is None:
        return None
    try:
        if candidate.options_bias == "Bearish":
            contracts = chain_provider.get_puts(candidate.symbol)
        else:
            contracts = chain_provider.get_calls(candidate.symbol)
    except Exception:
        return None

    eligible = [
        contract
        for contract in contracts
        if 30 <= contract.dte <= 240
        and contract.open_interest >= 100
        and contract.volume >= 10
        and contract.spread_pct <= 0.30
        and abs(contract.strike / candidate.close - 1.0) <= 0.20
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda contract: _contract_score(contract, candidate.close), reverse=True)
    return eligible[0]


def _contract_score(contract: OptionContract, close_proxy: float) -> float:
    strike_distance = abs(contract.strike / close_proxy - 1.0) if close_proxy > 0 else 1.0
    liquidity_score = min(contract.open_interest / 1000, 1.0) * 0.35
    volume_score = min(contract.volume / 250, 1.0) * 0.25
    spread_score = max(0.0, 1.0 - contract.spread_pct / 0.25) * 0.25
    strike_score = max(0.0, 1.0 - strike_distance / 0.20) * 0.15
    return liquidity_score + volume_score + spread_score + strike_score


def _liquidity_score(contract: OptionContract | None) -> float:
    if contract is None:
        return 0.0
    oi_score = min(contract.open_interest / 1000, 1.0) * 0.45
    volume_score = min(contract.volume / 250, 1.0) * 0.35
    spread_score = max(0.0, 1.0 - contract.spread_pct / 0.30) * 0.20
    return oi_score + volume_score + spread_score


def _liquidity_proxy(candidate: ScanCandidate) -> float:
    return max(0.0, min(candidate.metrics.relative_volume_20d / 1.5, 1.0))


def _idea_score(
    candidate: ScanCandidate,
    contract_score: float,
    liquidity_score: float,
) -> float:
    setup = composite_rank_score(candidate) * 0.45
    readiness = candidate.readiness_score * 0.20
    option_quality = contract_score * 0.20 if contract_score else liquidity_score * 0.10
    liquidity = liquidity_score * 0.15
    return max(0.0, min(setup + readiness + option_quality + liquidity, 1.0))


def _action_label(
    idea_score: float,
    candidate: ScanCandidate,
    contract: OptionContract | None,
) -> str:
    if candidate.setup_status == "Invalidated" or candidate.setup_score < 0.60:
        return "Avoid"
    if idea_score >= 0.78 and candidate.setup_status in {"Near Breakout", "Breakout"}:
        return "Trade Candidate"
    if idea_score >= 0.62:
        return "Watch"
    if contract is None:
        return "Needs Option Data"
    return "Avoid"


def _contract_liquidity_note(contract: OptionContract) -> str:
    if contract.open_interest >= 500 and contract.volume >= 100 and contract.spread_pct <= 0.15:
        return "Liquid contract"
    if contract.open_interest >= 100 and contract.spread_pct <= 0.25:
        return "Usable but verify spread"
    return "Weak contract liquidity"


def _risk_note(candidate: ScanCandidate, contract: OptionContract | None) -> str:
    notes: list[str] = []
    if candidate.weekly_context and candidate.weekly_context.is_extended:
        notes.append("weekly extended")
    if candidate.metrics.relative_volume_20d < 0.80:
        notes.append("low relative volume")
    if contract and contract.spread_pct > 0.20:
        notes.append("wide option spread")
    if contract and contract.implied_volatility >= 0.80:
        notes.append("high implied volatility")
    return ", ".join(notes) if notes else "Defined risk still required"


def _directional_strategy(candidate: WatchlistCandidate, quality: UnderlyingQualityProfile) -> str:
    if candidate.options_bias == "Bearish":
        return "Long put or put debit spread"
    if quality.gate in {"Pass", "Conditional"} and candidate.options_setup == "Call pullback":
        return "LEAPS/call spread or cash-secured put after trigger"
    if quality.gate in {"Pass", "Conditional"} and candidate.options_setup == "Call breakout":
        return "Call debit spread; covered-call eligible after extension"
    if quality.label in {"Institutional", "Core", "Quality Watch"}:
        return "Quality income watchlist; wait for EMA trigger"
    if candidate.options_setup == "Call breakout":
        return "Long call or call debit spread"
    if candidate.options_setup == "Call pullback":
        return "Call debit spread after reversal confirmation"
    return "Directional watchlist; wait for trigger"


def _directional_bucket(candidate: WatchlistCandidate, contract: OptionContract | None) -> str:
    if contract:
        if contract.dte <= 60:
            return "30-60 DTE"
        if contract.dte <= 120:
            return "60-120 DTE"
        return "120-240 DTE"
    if candidate.options_setup in {"Call breakout", "Put breakdown"}:
        return "30-90 DTE"
    return "60-180 DTE"


def _directional_idea_score(
    candidate: WatchlistCandidate,
    contract_score: float,
    liquidity_score: float,
    quality_score: float = 0.0,
    timing_score: float = 0.0,
) -> float:
    score = (
        candidate.readiness_score * 0.22
        + candidate.directional_score * 0.20
        + quality_score * 0.25
        + timing_score * 0.08
        + liquidity_score * 0.10
        + contract_score * 0.15
    )
    return max(0.0, min(score, 1.0))


def _directional_action_label(
    idea_score: float,
    candidate: WatchlistCandidate,
    contract: OptionContract | None,
    quality: UnderlyingQualityProfile | None = None,
    timing: EmaTimingSnapshot | None = None,
) -> str:
    if quality and quality.gate == "Fail":
        return "Avoid"
    if timing and timing.score < 0.50 and idea_score >= 0.58:
        return "Wait Timing"
    if quality and quality.gate in {"Conditional", "Review"} and idea_score >= 0.58:
        return "Quality Watch"
    if candidate.options_setup in {"Call breakout", "Put breakdown"} and idea_score >= 0.70:
        return "Trade Candidate"
    if idea_score >= 0.58:
        return "Watch"
    if contract is None:
        return "Needs Option Data"
    return "Avoid"


def _safe_fundamentals(
    symbol: str,
    fundamental_provider: FundamentalProvider | None,
) -> FundamentalSnapshot:
    if fundamental_provider is None:
        return FundamentalSnapshot()
    try:
        return fundamental_provider.get_fundamentals(symbol)
    except Exception:
        return FundamentalSnapshot()


def _safe_timing(
    symbol: str,
    timing_provider: EmaTimingProvider | None,
) -> EmaTimingSnapshot | None:
    if timing_provider is None:
        return None
    try:
        return timing_provider.get_timing(symbol)
    except Exception:
        return None


def _snapshot_number(value: float | None) -> float:
    return round(value, 4) if value is not None else 0.0


def _directional_quality(score: float) -> str:
    if score >= 0.80:
        return "Strong"
    if score >= 0.60:
        return "Watch"
    return "Weak"


def _directional_risk_note(candidate: WatchlistCandidate, contract: OptionContract | None) -> str:
    notes: list[str] = []
    if candidate.options_setup == "No clean setup":
        notes.append("wait for trigger")
    if candidate.relative_volume_20d < 1.0:
        notes.append("low RVOL")
    if candidate.options_bias == "Bearish" and candidate.regime_score >= 0.8:
        notes.append("bearish idea against constructive regime")
    if contract and contract.spread_pct > 0.20:
        notes.append("wide option spread")
    return ", ".join(notes) if notes else "Defined risk still required"
