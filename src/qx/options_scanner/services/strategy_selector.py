"""StrategySelector for QX Options Scanner V1.

Maps Direction Result + Volatility Result + Regime Context into continuous strategy fit scores.
Returns recommended strategy + alternate strategy with explanatory rationale.
"""

from typing import List, Tuple, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.services.direction_service import DirectionResult
from qx.options_scanner.services.volatility_service import VolatilityResult
from qx.options_scanner.models import RegimeContext


class StrategyFit(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_name: str
    fit_score: float = Field(description="0..100 Strategy Fit Score")
    category: str  # DEBIT | CREDIT | LEAP | WHEEL | SINGLE
    explanation: str


class StrategySelectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommended: StrategyFit
    alternate: StrategyFit
    all_ranked_strategies: List[StrategyFit]


class StrategySelector:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def evaluate_strategies(
        self,
        direction: DirectionResult,
        volatility: VolatilityResult,
        regime: RegimeContext
    ) -> StrategySelectionResult:
        dir_score = direction.score
        bias = direction.bias
        vol_class = volatility.classification
        iv_rv_ratio = volatility.iv_rv_ratio

        fits: List[StrategyFit] = []

        # 1. Bull Call Debit Spread
        bcds_fit = 50.0
        if bias == "BULLISH":
            bcds_fit += 30.0
            if vol_class in ("CHEAP", "FAIR"):
                bcds_fit += 20.0
        elif bias == "NEUTRAL":
            bcds_fit += 10.0
        fits.append(StrategyFit(
            strategy_name="Bull Call Debit Spread",
            fit_score=min(100.0, max(0.0, bcds_fit)),
            category="DEBIT",
            explanation="Defined-risk bullish spread capitalizing on low/fair implied volatility."
        ))

        # 2. Bull Put Credit Spread
        bpcs_fit = 50.0
        if bias == "BULLISH":
            bpcs_fit += 25.0
            if vol_class == "RICH":
                bpcs_fit += 25.0
        elif bias == "NEUTRAL":
            bpcs_fit += 15.0
        fits.append(StrategyFit(
            strategy_name="Bull Put Credit Spread",
            fit_score=min(100.0, max(0.0, bpcs_fit)),
            category="CREDIT",
            explanation="Defined-risk credit spread collecting overpriced volatility premium near bullish support."
        ))

        # 3. Long Call Single
        lc_fit = 40.0
        if bias == "BULLISH" and dir_score >= 75.0:
            lc_fit += 35.0
            if vol_class == "CHEAP":
                lc_fit += 25.0
        fits.append(StrategyFit(
            strategy_name="Long Call",
            fit_score=min(100.0, max(0.0, lc_fit)),
            category="SINGLE",
            explanation="Uncapped bullish directional exposure capitalizing on cheap implied volatility."
        ))

        # 4. Bear Put Debit Spread
        bpds_fit = 50.0
        if bias == "BEARISH":
            bpds_fit += 30.0
            if vol_class in ("CHEAP", "FAIR"):
                bpds_fit += 20.0
        fits.append(StrategyFit(
            strategy_name="Bear Put Debit Spread",
            fit_score=min(100.0, max(0.0, bpds_fit)),
            category="DEBIT",
            explanation="Defined-risk bearish spread capitalizing on breakdown momentum."
        ))

        # 5. Bear Call Credit Spread
        bccs_fit = 50.0
        if bias == "BEARISH":
            bccs_fit += 25.0
            if vol_class == "RICH":
                bccs_fit += 25.0
        fits.append(StrategyFit(
            strategy_name="Bear Call Credit Spread",
            fit_score=min(100.0, max(0.0, bccs_fit)),
            category="CREDIT",
            explanation="Defined-risk credit spread harvesting overpriced option volatility during selloffs."
        ))

        # 6. PMCC (Poor Man's Covered Call)
        pmcc_fit = 45.0
        if bias == "BULLISH":
            pmcc_fit += 30.0
            if vol_class in ("CHEAP", "FAIR"):
                pmcc_fit += 20.0
        fits.append(StrategyFit(
            strategy_name="PMCC (Poor Man's Covered Call)",
            fit_score=min(100.0, max(0.0, pmcc_fit)),
            category="LEAP",
            explanation="Long 365+ DTE ITM Call + Short 30 DTE Call selling to generate recurring theta cash flow."
        ))

        # 7. Cash-Secured Put / Wheel
        csp_fit = 40.0
        if bias in ("BULLISH", "NEUTRAL"):
            csp_fit += 25.0
            if vol_class == "RICH":
                csp_fit += 25.0
        fits.append(StrategyFit(
            strategy_name="Cash-Secured Put (Wheel)",
            fit_score=min(100.0, max(0.0, csp_fit)),
            category="WHEEL",
            explanation="Sells 30-45 DTE cash-secured puts at high IV to collect premium or take stock assignment."
        ))

        # Sort strategies by fit score descending
        ranked = sorted(fits, key=lambda s: s.fit_score, reverse=True)

        return StrategySelectionResult(
            recommended=ranked[0],
            alternate=ranked[1],
            all_ranked_strategies=ranked
        )
