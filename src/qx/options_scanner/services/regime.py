"""MarketRegimeContext Engine for QX Options Scanner V1."""

from datetime import datetime, timezone
from typing import Optional

from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.models import (
    MarketBiasEnum, RegimeContext, VIXTermStructureEnum
)


class RegimeService:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def build_regime_context(
        self,
        spx_close: float = 5000.0,
        vix_close: float = 15.0,
        vix_front_futures: float = 15.2,
        vix_back_futures: float = 16.5,
        es_overnight_move_pct: float = 0.0,
        now: Optional[datetime] = None
    ) -> RegimeContext:
        now_dt = now or datetime.now(timezone.utc)

        # VIX term structure: Contango (Front < Back) vs Backwardation (Front > Back)
        term_structure = VIXTermStructureEnum.CONTANGO
        if vix_front_futures > vix_back_futures:
            term_structure = VIXTermStructureEnum.BACKWARDATION

        # Determine overall market bias
        if vix_close > 28.0 or term_structure == VIXTermStructureEnum.BACKWARDATION:
            bias = MarketBiasEnum.BEARISH
        elif es_overnight_move_pct > 0.002 and vix_close < 20.0:
            bias = MarketBiasEnum.BULLISH
        elif es_overnight_move_pct < -0.005:
            bias = MarketBiasEnum.BEARISH
        else:
            bias = MarketBiasEnum.NEUTRAL

        return RegimeContext(
            as_of=now_dt,
            market_bias=bias,
            vix_close=vix_close,
            vix_term_structure=term_structure,
            spx_close=spx_close,
            es_overnight_move_pct=es_overnight_move_pct
        )
