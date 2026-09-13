"""VolatilityService for QX Options Scanner V1.

Uses EWMA realized volatility forecasting to calculate vol_edge and iv_rv_ratio.
Classifies volatility state (CHEAP / FAIR / RICH) and computes normalized 0..100 volatility score.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
import numpy as np

from qx.options_scanner.config import ScannerConfig


class VolatilityComponents(BaseModel):
    model_config = ConfigDict(frozen=True)

    iv_rank_percentile: float = Field(default=50.0, description="0-100 score")
    iv_vs_forecast_rv: float = Field(default=50.0, description="0-100 score")
    skew_25d: float = Field(default=50.0, description="0-100 score")
    term_structure: float = Field(default=50.0, description="0-100 score")
    expected_move_fit: float = Field(default=50.0, description="0-100 score")


class VolatilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float = Field(description="Normalized 0..100 Volatility Score")
    classification: Literal["CHEAP", "FAIR", "RICH"]
    current_iv: float
    forecast_rv: float
    vol_edge: float = Field(description="IV - forecast_RV")
    iv_rv_ratio: float = Field(description="IV / forecast_RV")
    iv_rank: float
    components: VolatilityComponents


class VolatilityService:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def calculate_ewma_realized_vol(self, daily_returns: List[float]) -> float:
        """Calculates EWMA annualized realized volatility proxy."""
        if not daily_returns or len(daily_returns) < 5:
            return 0.15  # 15% default baseline

        returns = np.array(daily_returns)
        span = self.config.ewma.span
        alpha = 2.0 / (span + 1.0)
        
        # Calculate EWMA variance
        weights = (1 - alpha) ** np.arange(len(returns))[::-1]
        weights /= weights.sum()
        variance = np.sum(weights * (returns ** 2))
        annualized_vol = np.sqrt(variance) * self.config.ewma.annualization_factor
        return float(round(annualized_vol, 4))

    def calculate_volatility_context(
        self,
        current_iv: float,
        daily_returns: List[float],
        iv_rank: float = 50.0,
        skew_25d_score: float = 50.0,
        term_structure_score: float = 50.0,
        expected_move_fit_score: float = 50.0
    ) -> VolatilityResult:
        w = self.config.volatility_weights

        forecast_rv = self.calculate_ewma_realized_vol(daily_returns)
        if forecast_rv <= 0.0001:
            forecast_rv = 0.15

        vol_edge = round(current_iv - forecast_rv, 4)
        iv_rv_ratio = round(current_iv / forecast_rv, 4)

        # Classification continuous bands
        if iv_rv_ratio < 0.95:
            classification = "CHEAP"
            iv_vs_rv_score = max(0.0, min(100.0, 90.0 - (iv_rv_ratio * 40.0)))
        elif iv_rv_ratio <= 1.20:
            classification = "FAIR"
            iv_vs_rv_score = 50.0
        else:
            classification = "RICH"
            iv_vs_rv_score = max(0.0, min(100.0, (iv_rv_ratio - 1.20) * 80.0 + 50.0))

        comp = VolatilityComponents(
            iv_rank_percentile=max(0.0, min(100.0, iv_rank)),
            iv_vs_forecast_rv=max(0.0, min(100.0, iv_vs_rv_score)),
            skew_25d=max(0.0, min(100.0, skew_25d_score)),
            term_structure=max(0.0, min(100.0, term_structure_score)),
            expected_move_fit=max(0.0, min(100.0, expected_move_fit_score))
        )

        score = (
            comp.iv_rank_percentile * w.iv_rank_percentile +
            comp.iv_vs_forecast_rv * w.iv_vs_forecast_rv +
            comp.skew_25d * w.skew_25d +
            comp.term_structure * w.term_structure +
            comp.expected_move_fit * w.expected_move_fit
        )

        score = round(max(0.0, min(100.0, score)), 2)

        return VolatilityResult(
            score=score,
            classification=classification,
            current_iv=round(current_iv, 4),
            forecast_rv=forecast_rv,
            vol_edge=vol_edge,
            iv_rv_ratio=iv_rv_ratio,
            iv_rank=round(iv_rank, 2),
            components=comp
        )
