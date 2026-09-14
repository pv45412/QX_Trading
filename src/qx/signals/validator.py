"""Multi-factor technical signal validator for Phase 3 Signal Quality & Validation.

Evaluates trade setup candidates across structure (BOS/CHoCH), liquidity (FVG),
volume dynamics (VWAP/RVOL), and macro context (Sector Rotation).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    WEAK_ALIGNMENT = "WEAK_ALIGNMENT"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class FactorScore:
    factor_name: str
    score: float  # 0.0 to 100.0
    weight: float
    passed: bool
    detail: str


@dataclass(frozen=True)
class SignalValidationResult:
    symbol: str
    timeframe: str
    composite_score: float  # 0.0 to 100.0
    status: ValidationStatus
    factors: List[FactorScore]
    summary: str


class SignalValidator:
    """Validates trade signals against multi-factor market evidence."""

    def __init__(
        self,
        min_rvol: float = 1.5,
        min_composite_score: float = 70.0,
    ) -> None:
        self.min_rvol = min_rvol
        self.min_composite_score = min_composite_score

    def validate_signal(
        self,
        symbol: str,
        trend_bias: str,
        price: float,
        rvol: float = 1.0,
        vwap: Optional[float] = None,
        bos_confirmed: bool = False,
        fvg_present: bool = False,
        sector_relative_strength: float = 0.0,
        timeframe: str = "1D",
    ) -> SignalValidationResult:
        factors: List[FactorScore] = []
        is_bullish = trend_bias.upper() == "BULLISH"

        # 1. Structure (BOS / CHoCH) - Weight 0.35
        bos_score = 95.0 if bos_confirmed else 40.0
        factors.append(
            FactorScore(
                factor_name="Structure (BOS/CHoCH)",
                score=bos_score,
                weight=0.35,
                passed=bos_confirmed,
                detail="Break of structure confirmed on timeframe"
                if bos_confirmed
                else "No structure break confirmed",
            )
        )

        # 2. Volume Expansion (RVOL) - Weight 0.25
        rvol_passed = rvol >= self.min_rvol
        rvol_score = min(100.0, (rvol / max(self.min_rvol, 1.0)) * 75.0) if rvol > 0 else 30.0
        factors.append(
            FactorScore(
                factor_name="Relative Volume (RVOL)",
                score=round(rvol_score, 1),
                weight=0.25,
                passed=rvol_passed,
                detail=f"RVOL {rvol:.2f}x vs threshold {self.min_rvol}x",
            )
        )

        # 3. VWAP Alignment - Weight 0.20
        if vwap is not None and vwap > 0:
            vwap_aligned = (price >= vwap) if is_bullish else (price <= vwap)
            vwap_score = 90.0 if vwap_aligned else 35.0
            vwap_detail = f"Price ${price:.2f} {'above' if price >= vwap else 'below'} VWAP ${vwap:.2f}"
        else:
            vwap_aligned = True
            vwap_score = 70.0
            vwap_detail = "VWAP benchmark unavailable"

        factors.append(
            FactorScore(
                factor_name="VWAP Positioning",
                score=vwap_score,
                weight=0.20,
                passed=vwap_aligned,
                detail=vwap_detail,
            )
        )

        # 4. Fair Value Gap & Sector Rotation - Weight 0.20
        macro_passed = fvg_present or sector_relative_strength > 0
        macro_score = 85.0 if macro_passed else 50.0
        factors.append(
            FactorScore(
                factor_name="FVG & Sector Alignment",
                score=macro_score,
                weight=0.20,
                passed=macro_passed,
                detail=f"FVG present: {fvg_present}, Sector RS: {sector_relative_strength:+.2f}%",
            )
        )

        # Calculate weighted composite score
        composite = sum(f.score * f.weight for f in factors)
        composite_score = round(composite, 1)

        if composite_score >= self.min_composite_score and bos_confirmed:
            status = ValidationStatus.VALIDATED
        elif composite_score >= 55.0:
            status = ValidationStatus.WEAK_ALIGNMENT
        else:
            status = ValidationStatus.INVALIDATED

        summary = (
            f"Signal {symbol} ({trend_bias}) scored {composite_score:.1f}/100 [{status.value}]. "
            f"BOS: {bos_confirmed}, RVOL: {rvol:.2f}x."
        )

        return SignalValidationResult(
            symbol=symbol,
            timeframe=timeframe,
            composite_score=composite_score,
            status=status,
            factors=factors,
            summary=summary,
        )
