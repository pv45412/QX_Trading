"""Market Structure Detection Engine (re-exports from canonical qx.structure)."""

from qx.structure import (
    FairValueGap,
    StructureAnalysisResult,
    detect_fair_value_gaps,
    analyze_market_structure,
)

__all__ = [
    "FairValueGap",
    "StructureAnalysisResult",
    "detect_fair_value_gaps",
    "analyze_market_structure",
]

