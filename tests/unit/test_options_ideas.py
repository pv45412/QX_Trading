from datetime import date, timedelta
from dataclasses import replace
from pathlib import Path

import pytest

from qx.options.chains import OptionContract
from qx.options.ideas import (
    build_option_trade_plan,
    evaluate_underlying_quality,
    generate_directional_option_ideas,
    generate_option_ideas,
    option_ideas_frame,
)
from qx.options.quality import FundamentalSnapshot
from qx.options.timing import EmaTimingSnapshot
from qx.patterns.rectangle import analyze_rectangle
from qx.ui.pages.options_ideas import (
    filter_options_frame,
    options_action_frame,
    options_bucket_frame,
    options_quality_gap_frame,
    options_quality_triage_frame,
    options_regime_strategy_frame,
    options_strategy_playbook_frame,
    summarize_options_frame,
    validate_option_chain_frame,
)
from qx.watchlist.engine import build_broad_watchlist
from tests.unit.test_rectangle import _clean_rectangle_bars
from tests.unit.test_watchlist import StaticMetadata, WatchlistProvider


@pytest.fixture(autouse=True)
def _isolate_watchlist_failure_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qx.watchlist.engine.WATCHLIST_FAILURE_CACHE", tmp_path / "watchlist_failures.csv")


class StaticChainProvider:
    def get_calls(self, symbol: str) -> list[OptionContract]:
        return [
            OptionContract(
                symbol=symbol,
                expiration=date.today() + timedelta(days=60),
                contract_symbol=f"{symbol}260101C00100000",
                strike=100.0,
                option_type="call",
                bid=4.9,
                ask=5.1,
                last_price=5.0,
                volume=250,
                open_interest=500,
                implied_volatility=0.35,
                dte=60,
            )
        ]

    def get_puts(self, symbol: str) -> list[OptionContract]:
        return [
            OptionContract(
                symbol=symbol,
                expiration=date.today() + timedelta(days=60),
                contract_symbol=f"{symbol}260101P00100000",
                strike=100.0,
                option_type="put",
                bid=4.9,
                ask=5.1,
                last_price=5.0,
                volume=250,
                open_interest=500,
                implied_volatility=0.35,
                dte=60,
            )
        ]


class StaticFundamentalProvider:
    def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        return FundamentalSnapshot(
            market_cap=80_000_000_000,
            eps_growth=0.20,
            revenue_growth=0.12,
            roe=0.28,
            debt_to_equity=0.40,
            profit_margin=0.22,
            free_cash_flow_positive=True,
        )


class StaticTimingProvider:
    def get_timing(self, symbol: str) -> EmaTimingSnapshot:
        return EmaTimingSnapshot(
            score=0.90,
            label="Aligned",
            trigger="Trigger active",
            alignment="D5 up; H50 held; 30m21 above; 15m8 above",
            note="Fractal EMA stack is aligned for execution.",
        )


def test_generate_option_ideas_from_scanner_candidates() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())

    ideas = generate_option_ideas([candidate])
    frame = option_ideas_frame(ideas)

    assert ideas
    assert ideas[0].symbol == "TEST"
    assert ideas[0].direction == "Bullish"
    assert ideas[0].action
    assert ideas[0].strategy
    assert "bucket" in frame.columns
    assert "idea_score" in frame.columns


def test_generate_option_ideas_can_attach_contract_data() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())

    ideas = generate_option_ideas([candidate], chain_provider=StaticChainProvider())

    assert ideas[0].contract_symbol == "TEST260101C00100000"
    assert ideas[0].dte == 60
    assert ideas[0].spread_pct > 0
    assert ideas[0].contract_score > 0


def test_generate_directional_option_ideas_from_watchlist() -> None:
    watchlist = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=StaticMetadata(),
    )

    ideas = generate_directional_option_ideas(
        watchlist.candidates,
        chain_provider=StaticChainProvider(),
        fundamental_provider=StaticFundamentalProvider(),
        timing_provider=StaticTimingProvider(),
        min_directional_score=0.30,
    )
    frame = option_ideas_frame(ideas)

    assert ideas
    assert ideas[0].source == "Broad Directional"
    assert ideas[0].direction in {"Bullish", "Bearish"}
    assert ideas[0].score == watchlist.candidates[0].readiness_score
    assert f"readiness {watchlist.candidates[0].readiness_score:.2f}" in ideas[0].rationale
    assert ideas[0].directional_score > 0
    assert ideas[0].underlying_quality_score > 0
    assert ideas[0].underlying_quality in {"Institutional", "Core", "Quality Watch", "Speculative", "Reject"}
    assert ideas[0].income_suitability
    assert ideas[0].technical_timing
    assert ideas[0].quality_breakdown
    assert ideas[0].quality_missing != "real fundamentals unavailable"
    assert ideas[0].market_cap > 0
    assert ideas[0].eps_growth > 0
    assert ideas[0].timing_score == 0.90
    assert ideas[0].timing_label == "Aligned"
    assert ideas[0].regime_bucket
    assert ideas[0].strategy_reason
    assert ideas[0].exit_plan
    assert "options_bias" in frame.columns
    assert "underlying_quality_score" in frame.columns
    assert "regime_bucket" in frame.columns


def test_options_summary_counts_quality_and_timing_metrics() -> None:
    watchlist = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=StaticMetadata(),
    )

    ideas = generate_directional_option_ideas(
        watchlist.candidates,
        chain_provider=StaticChainProvider(),
        fundamental_provider=StaticFundamentalProvider(),
        timing_provider=StaticTimingProvider(),
        min_directional_score=0.30,
    )
    frame = option_ideas_frame(ideas)

    summary = summarize_options_frame(frame)

    assert summary["fundamental_coverage"] == 1
    assert summary["timing_aligned"] == 1
    assert summary["core_quality"] + int((frame["underlying_quality"] == "Quality Watch").sum()) >= 1


def test_options_quality_triage_and_gap_frames_surface_fundamental_readiness() -> None:
    watchlist = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=StaticMetadata(),
    )

    ideas = generate_directional_option_ideas(
        watchlist.candidates,
        chain_provider=StaticChainProvider(),
        fundamental_provider=StaticFundamentalProvider(),
        timing_provider=StaticTimingProvider(),
        min_directional_score=0.30,
    )
    frame = option_ideas_frame(ideas)

    triage = options_quality_triage_frame(frame)
    gaps = options_quality_gap_frame(frame)

    assert triage["ideas"].sum() == 1
    assert triage["real_fundamentals"].sum() == 1
    assert triage["avg_quality_score"].iloc[0] > 0
    assert gaps["has_fundamentals"].iloc[0]
    assert gaps["quality_missing"].iloc[0] != "real fundamentals unavailable"


def test_underlying_quality_model_uses_real_fundamental_slots_when_available() -> None:
    watchlist = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=StaticMetadata(),
    )

    quality = evaluate_underlying_quality(
        watchlist.candidates[0],
        fundamentals=FundamentalSnapshot(
            market_cap=80_000_000_000,
            eps_growth=0.20,
            revenue_growth=0.12,
            roe=0.28,
            debt_to_equity=0.40,
            profit_margin=0.22,
            free_cash_flow_positive=True,
        ),
    )

    assert quality.factor_scores["business_quality"] > 0.75
    assert quality.factor_grades["business_quality"] in {"A", "B"}
    assert "real fundamentals unavailable" not in quality.missing
    assert quality.breakdown


def test_underlying_quality_gate_rejects_low_liquidity_income_names() -> None:
    watchlist = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=StaticMetadata(),
    )
    weak_candidate = replace(
        watchlist.candidates[0],
        close=10.0,
        avg_volume_20d=100_000,
        liquidity_score=0.05,
        trend_score=0.40,
        final_score=0.30,
    )

    quality = evaluate_underlying_quality(weak_candidate)
    ideas = generate_directional_option_ideas(
        [weak_candidate],
        chain_provider=StaticChainProvider(),
        min_directional_score=0.30,
    )

    assert quality.label == "Reject"
    assert quality.gate == "Fail"
    assert "avg volume < 1M" in quality.missing
    assert "real fundamentals unavailable" in quality.missing
    assert ideas[0].action == "Avoid"
    assert ideas[0].income_suitability == "Avoid income"


def test_options_page_summary_and_filters() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    ideas = generate_option_ideas([candidate], chain_provider=StaticChainProvider())
    frame = option_ideas_frame(ideas)

    summary = summarize_options_frame(frame)
    filtered = filter_options_frame(
        frame,
        actions=[ideas[0].action],
        directions=["Bullish"],
        sources=["Rectangle"],
        buckets=[ideas[0].bucket],
        min_score=0.0,
        max_spread=1.0,
        min_open_interest=100,
        ticker_query="TES",
    )
    bucket_frame = options_bucket_frame(frame)
    regime_frame = options_regime_strategy_frame(frame)
    playbook_frame = options_strategy_playbook_frame()
    action_frame = options_action_frame(frame)

    assert summary["ideas"] == 1
    assert len(filtered) == 1
    assert bucket_frame["ideas"].iloc[0] == 1
    assert regime_frame["ideas"].iloc[0] == 1
    assert "regime_bucket" in regime_frame.columns
    assert {"Long call", "Debit spread", "Credit spread"}.issubset(set(playbook_frame["instrument"]))
    assert action_frame["ideas"].iloc[0] == 1


def test_option_trade_plan_and_chain_validation() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    ideas = generate_option_ideas([candidate], chain_provider=StaticChainProvider())
    frame = option_ideas_frame(ideas)

    plan = build_option_trade_plan(ideas[0])
    validation = validate_option_chain_frame(frame, chain_source="schwab")

    assert plan.symbol == "TEST"
    assert plan.entry_checklist
    assert any("Regime strategy bucket" in item for item in plan.entry_checklist)
    assert validation["source"] == "schwab"
    assert validation["attached_contracts"] == 1
