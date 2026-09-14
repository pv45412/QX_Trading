"""Decoupled 4-Tier Trade Scorer for QX Options Scanner.

Preserves explicit separation between:
1. signal_quality_score (technical structure quality: BOS, RVOL, VWAP, FVG)
2. portfolio_fit_score (concentration, sector allocation fit)
3. risk_score (account risk limit fit)
4. final_trade_score (composite trade recommendation)

Never hides portfolio vetoes inside the technical setup score.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TradeScoreBreakdown:
    symbol: str
    signal_quality_score: float  # 0.0 to 100.0 (Pure technical pattern setup)
    portfolio_fit_score: float   # 0.0 to 100.0 (Portfolio & sector concentration fit)
    risk_score: float            # 0.0 to 100.0 (Account equity & stop loss risk fit)
    final_trade_score: float     # 0.0 to 100.0 (Composite final score)
    is_vetoed: bool
    veto_reason: Optional[str]
    summary: str


class DecoupledTradeScorer:
    """Calculates decoupled trade score components without obscuring technical signal quality."""

    def __init__(
        self,
        weight_signal: float = 0.50,
        weight_fit: float = 0.30,
        weight_risk: float = 0.20,
    ) -> None:
        self.weight_signal = weight_signal
        self.weight_fit = weight_fit
        self.weight_risk = weight_risk

    def calculate_score_breakdown(
        self,
        symbol: str,
        technical_signal_score: float,
        current_sector_exposure_pct: float,
        proposed_addition_pct: float = 0.0,
        max_sector_limit_pct: float = 25.0,
        defined_risk_per_trade: float = 2500.0,
        max_allowable_risk: float = 2500.0,
        veto_reason: Optional[str] = None,
    ) -> TradeScoreBreakdown:
        is_vetoed = veto_reason is not None

        # 1. Technical signal score (0 to 100)
        signal_quality_score = round(max(0.0, min(100.0, technical_signal_score)), 1)

        # 2. Portfolio fit score (0 to 100)
        projected_sector_exposure = current_sector_exposure_pct + proposed_addition_pct
        if projected_sector_exposure >= max_sector_limit_pct:
            portfolio_fit_score = 0.0
        else:
            remaining_headroom = max_sector_limit_pct - projected_sector_exposure
            portfolio_fit_score = round(min(100.0, (remaining_headroom / max_sector_limit_pct) * 100.0), 1)

        # 3. Risk score (0 to 100)
        if max_allowable_risk <= 0:
            risk_score = 0.0
        elif defined_risk_per_trade > max_allowable_risk:
            risk_score = max(0.0, round(100.0 - ((defined_risk_per_trade - max_allowable_risk) / max_allowable_risk) * 100.0, 1))
        else:
            risk_score = 100.0

        # 4. Composite final trade score
        if is_vetoed:
            final_trade_score = 0.0
        else:
            final_trade_score = round(
                (signal_quality_score * self.weight_signal)
                + (portfolio_fit_score * self.weight_fit)
                + (risk_score * self.weight_risk),
                1,
            )

        summary = (
            f"TradeScore for {symbol}: Signal Quality {signal_quality_score}/100, "
            f"Portfolio Fit {portfolio_fit_score}/100, Risk {risk_score}/100 -> "
            f"Final Score: {final_trade_score}/100" + (f" [VETOED: {veto_reason}]" if is_vetoed else "")
        )

        return TradeScoreBreakdown(
            symbol=symbol,
            signal_quality_score=signal_quality_score,
            portfolio_fit_score=portfolio_fit_score,
            risk_score=risk_score,
            final_trade_score=final_trade_score,
            is_vetoed=is_vetoed,
            veto_reason=veto_reason,
            summary=summary,
        )
