"""StructureScoringService (Direction Composite Engine) for QX Options Scanner V1.

Weighted continuous score (0..100) combining 7 market structure components:
25% Market Structure (BOS/CHoCH)
15% VWAP Alignment
15% EMA Slope & Alignment
15% RVOL
15% Cumulative Delta / Buying Pressure
10% FVG Quality
 5% Relative Strength vs SPY
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from qx.options_scanner.config import ScannerConfig


class DirectionScoreComponents(BaseModel):
    model_config = ConfigDict(frozen=True)

    market_structure_bos_choch: float = Field(default=50.0, description="0-100 score")
    vwap_alignment: float = Field(default=50.0, description="0-100 score")
    ema_slope_alignment: float = Field(default=50.0, description="0-100 score")
    rvol: float = Field(default=50.0, description="0-100 score")
    cumulative_delta: float = Field(default=50.0, description="0-100 score")
    fvg_quality: float = Field(default=50.0, description="0-100 score")
    relative_strength: float = Field(default=50.0, description="0-100 score")


class DirectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float = Field(description="Normalized 0..100 Direction Score")
    bias: str = Field(description="BULLISH | BEARISH | NEUTRAL")
    components: DirectionScoreComponents


class DirectionService:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def calculate_direction_score(
        self,
        bos_choch: float = 50.0,
        vwap: float = 50.0,
        ema: float = 50.0,
        rvol: float = 50.0,
        cum_delta: float = 50.0,
        fvg: float = 50.0,
        rs: float = 50.0
    ) -> DirectionResult:
        w = self.config.direction_weights

        # Clamp components to 0..100
        comp = DirectionScoreComponents(
            market_structure_bos_choch=max(0.0, min(100.0, bos_choch)),
            vwap_alignment=max(0.0, min(100.0, vwap)),
            ema_slope_alignment=max(0.0, min(100.0, ema)),
            rvol=max(0.0, min(100.0, rvol)),
            cumulative_delta=max(0.0, min(100.0, cum_delta)),
            fvg_quality=max(0.0, min(100.0, fvg)),
            relative_strength=max(0.0, min(100.0, rs)),
        )

        score = (
            comp.market_structure_bos_choch * w.market_structure_bos_choch +
            comp.vwap_alignment * w.vwap_alignment +
            comp.ema_slope_alignment * w.ema_slope_alignment +
            comp.rvol * w.rvol +
            comp.cumulative_delta * w.cumulative_delta +
            comp.fvg_quality * w.fvg_quality +
            comp.relative_strength * w.relative_strength
        )

        score = round(max(0.0, min(100.0, score)), 2)

        if score >= 60.0:
            bias = "BULLISH"
        elif score <= 40.0:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return DirectionResult(score=score, bias=bias, components=comp)
