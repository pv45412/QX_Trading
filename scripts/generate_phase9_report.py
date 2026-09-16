import os
import json
from datetime import datetime

from qx.config.rules_config import RulesEngineConfig
from qx.tradeability.models import TradeabilityResult, TradeabilityState
from qx.models.rules import PublicationState
from qx.options_expression.models import (
    OptionsContext,
    OptionContract,
    OptionGreeks,
    OptionsExpressionState,
    StrategyType,
    OptionGreekProvenance
)
from qx.options_expression.engine import OptionsExpressionEngine

def make_tr(direction="BULLISH", targets=None, state=TradeabilityState.TRADEABLE):
    if targets is None:
        targets = [110.0] if direction == "BULLISH" else [90.0]
    return TradeabilityResult(
        tradeability_id="trade_eval_123",
        triggered_setup_id="setup_123",
        playbook_id="playbook_a_pullback",
        symbol="NVDA",
        timeframe="5m",
        direction=direction,
        state=state,
        publication_state=PublicationState.VERIFIED,
        trigger_price=100.0,
        observed_underlying_price=100.0,
        observed_entry_reference_price=100.0,
        invalidation_price=90.0 if direction == "BULLISH" else 110.0,
        target_candidates=targets,
        participation_score=100.0,
        participation_evidence_coverage=1.0,
        delta_score=100.0,
        delta_reliability=1.0,
        extension_atr=0.5,
        spread_absolute=0.1,
        spread_pct=0.001,
        liquidity_status="TIGHT",
        risk_reward_to_target1=2.0,
        risk_reward_to_best_structural_target=2.0,
        gap_beyond_trigger=False,
        gap_distance_atr=0.0,
        bars_since_trigger=0,
        seconds_since_trigger=0.0,
        triggered_at="2026-09-15T10:00:00Z",
        tradeability_evaluated_at="2026-09-15T10:00:00Z",
        evaluated_at="2026-09-15T10:00:00Z",
        data_as_of="2026-09-15T10:00:00Z",
        reason_codes=[],
        evidence_ladder={},
        config_version="research_v1",
        engine_version="v8.0.0",
        trade_state="NONE - OPTIONS EXPRESSION NOT YET EVALUATED"
    )

def make_ctx(iv_rank=30.0, expiration="2026-10-15", dte=30, spread=0.1, event=None, quote_age=0.0, greek_prov="BROKER_PROVIDED"):
    prov = OptionGreekProvenance.BROKER_PROVIDED if greek_prov == "BROKER_PROVIDED" else OptionGreekProvenance.MODEL_CALCULATED
    
    chain = {
        expiration: {
            # ATM
            100.0: {
                "CALL": OptionContract(
                    symbol=f"NVDA_{expiration.replace('-','')}C100", underlying_symbol="NVDA", strike=100.0,
                    expiration=expiration, dte=dte, is_call=True, bid=5.0, ask=5.0+spread, mark=5.0+(spread/2), volume=1000, open_interest=5000,
                    greeks=OptionGreeks(delta=0.50, provenance=prov), quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=quote_age, contract_multiplier=100.0
                ),
                "PUT": OptionContract(
                    symbol=f"NVDA_{expiration.replace('-','')}P100", underlying_symbol="NVDA", strike=100.0,
                    expiration=expiration, dte=dte, is_call=False, bid=5.0, ask=5.0+spread, mark=5.0+(spread/2), volume=1000, open_interest=5000,
                    greeks=OptionGreeks(delta=-0.50, provenance=prov), quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=quote_age, contract_multiplier=100.0
                )
            },
            # OTM
            105.0: {
                 "CALL": OptionContract(
                    symbol=f"NVDA_{expiration.replace('-','')}C105", underlying_symbol="NVDA", strike=105.0,
                    expiration=expiration, dte=dte, is_call=True, bid=2.5, ask=2.5+spread, mark=2.5+(spread/2), volume=1000, open_interest=5000,
                    greeks=OptionGreeks(delta=0.30, provenance=prov), quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=quote_age, contract_multiplier=100.0
                )
            },
            95.0: {
                 "PUT": OptionContract(
                    symbol=f"NVDA_{expiration.replace('-','')}P95", underlying_symbol="NVDA", strike=95.0,
                    expiration=expiration, dte=dte, is_call=False, bid=2.5, ask=2.5+spread, mark=2.5+(spread/2), volume=1000, open_interest=5000,
                    greeks=OptionGreeks(delta=-0.30, provenance=prov), quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=quote_age, contract_multiplier=100.0
                )
            },
            # FAR OTM (Target)
            110.0: {
                 "CALL": OptionContract(
                    symbol=f"NVDA_{expiration.replace('-','')}C110", underlying_symbol="NVDA", strike=110.0,
                    expiration=expiration, dte=dte, is_call=True, bid=1.0, ask=1.0+spread, mark=1.0+(spread/2), volume=100, open_interest=500,
                    greeks=OptionGreeks(delta=0.15, provenance=prov), quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=quote_age, contract_multiplier=100.0
                )
            },
            90.0: {
                 "PUT": OptionContract(
                    symbol=f"NVDA_{expiration.replace('-','')}P90", underlying_symbol="NVDA", strike=90.0,
                    expiration=expiration, dte=dte, is_call=False, bid=1.0, ask=1.0+spread, mark=1.0+(spread/2), volume=100, open_interest=500,
                    greeks=OptionGreeks(delta=-0.15, provenance=prov), quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=quote_age, contract_multiplier=100.0
                )
            }
        }
    }
    
    events = []
    if event:
        events.append(event)
        
    return OptionsContext(
        underlying_symbol="NVDA",
        underlying_price=100.0,
        data_as_of="2026-09-15T10:00:00Z",
        chain=chain,
        iv_rank=iv_rank,
        events=events
    )

scenarios = [
    ("1. Bullish low-IV liquid chain", make_tr("BULLISH"), make_ctx(iv_rank=20.0)),
    ("2. Bullish high-IV liquid chain", make_tr("BULLISH"), make_ctx(iv_rank=80.0)),
    ("3. Bearish low-IV liquid chain", make_tr("BEARISH"), make_ctx(iv_rank=20.0)),
    ("4. Bearish high-IV liquid chain", make_tr("BEARISH"), make_ctx(iv_rank=80.0)),
    ("5. Stale option chain", make_tr("BULLISH"), make_ctx(quote_age=120.0)),
    ("6. One-leg-illiquid debit spread", make_tr("BULLISH"), make_ctx(spread=0.5)),
    ("7. No valid expiration", make_tr("BULLISH"), make_ctx(dte=90)),
    ("8. No valid strike", make_tr("BULLISH"), make_ctx(greek_prov="MODEL_CALCULATED")), # Will manually alter deltas
    ("9. Earnings before expiration", make_tr("BULLISH"), make_ctx(event={"event_type": "earnings", "event_date": "2026-10-01"})),
    ("10. Structural target too close for useful spread", make_tr("BULLISH", targets=[101.0]), make_ctx()),
    ("11. IV Rank unavailable", make_tr("BULLISH"), make_ctx(iv_rank=None)),
    ("12. Model-calculated Greeks", make_tr("BULLISH"), make_ctx(greek_prov="MODEL_CALCULATED"))
]

engine = OptionsExpressionEngine()

with open("c:/Project/2026/phase9_1_report.md", "w") as f:
    f.write("# Phase 9.1 Characterization Report\\n\\n")
    
    for name, tr, ctx in scenarios:
        # Tweak for scenario 8
        if "No valid strike" in name:
            for s in ctx.chain["2026-10-15"].values():
                if "CALL" in s: s["CALL"].greeks.delta = 0.99
                if "PUT" in s: s["PUT"].greeks.delta = -0.99
                
        # Tweak for scenario 6
        if "One-leg-illiquid" in name:
             ctx.chain["2026-10-15"][110.0]["CALL"].ask = 3.0 # make it huge spread
             ctx.chain["2026-10-15"][100.0]["CALL"].ask = 5.1 # normal
             
        res = engine.evaluate_options_expression(tr, ctx)
        
        f.write(f"## {name}\\n")
        f.write(f"- **Phase 8 Direction**: {tr.direction}\\n")
        f.write(f"- **Final State**: {res.state.value}\\n")
        if res.reason_codes:
            f.write(f"- **Reason Codes**: {', '.join(res.reason_codes)}\\n")
        f.write(f"- **IV Rank**: {res.iv_rank if res.iv_rank is not None else 'UNAVAILABLE'}\\n")
        
        if res.candidate_strategies:
            cand = res.candidate_strategies[0] # Primary
            f.write(f"\\n### Primary Candidate: {cand.strategy_type.value}\\n")
            f.write(f"- **Expiry / DTE**: {cand.expiration} ({cand.dte} DTE)\\n")
            f.write(f"- **Strikes**: {[leg.strike for leg in cand.legs]}\\n")
            f.write(f"- **Legs**: {[str(leg.strike) + (' C' if leg.is_call else ' P') for leg in cand.legs]}\\n")
            f.write(f"- **Bid/Ask**: {[(leg.bid, leg.ask) for leg in cand.legs]}\\n")
            f.write(f"- **OI / Volume**: {[(leg.open_interest, leg.volume) for leg in cand.legs]}\\n")
            f.write(f"- **IV / IV Rank / IV Pct**: {res.iv} / {res.iv_rank} / {res.iv_percentile}\\n")
            f.write(f"- **Greeks (Combined)**: D:{cand.combined_delta} G:{cand.combined_gamma} T:{cand.combined_theta} V:{cand.combined_vega}\\n")
            f.write(f"- **Greek Provenance**: {cand.legs[0].greeks.provenance.value}\\n")
            f.write(f"- **Natural Price**: {cand.natural_price}\\n")
            f.write(f"- **Midpoint Price**: {cand.midpoint_price}\\n")
            f.write(f"- **Conservative Fill**: {cand.conservative_fill_estimate}\\n")
            f.write(f"- **Net Debit/Credit**: {cand.net_debit if cand.net_debit else cand.net_credit}\\n")
            f.write(f"- **Max Loss**: {cand.max_loss}\\n")
            f.write(f"- **Max Profit**: {cand.max_profit}\\n")
            f.write(f"- **Breakeven**: {cand.breakeven_points}\\n")
            f.write(f"- **Structural Target Fit**: {cand.structural_target_fit}\\n")
            f.write(f"- **Event Risk Identified**: {cand.event_risk_identified}\\n")
            f.write(f"- **Strategy Fit Score**: {cand.strategy_fit_score}\\n")
        else:
            f.write(f"\\n*(No valid candidates generated)*\\n")
            
        f.write("\\n---\\n\\n")

