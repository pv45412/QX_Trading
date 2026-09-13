"""Unit tests for StrategySelector, TradeConstructor, and RiskService."""

from datetime import datetime, timezone
import pytest

from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.models import (
    UnderlyingQuote, OptionContract, OptionChain, OptionTypeEnum, RegimeContext
)
from qx.options_scanner.services.direction_service import DirectionService
from qx.options_scanner.services.volatility_service import VolatilityService
from qx.options_scanner.services.strategy_selector import StrategySelector
from qx.options_scanner.services.trade_constructor import TradeConstructor
from qx.options_scanner.services.risk_service import RiskService


def test_strategy_selection_and_risk_sizing():
    config = ScannerConfig()
    ds = DirectionService(config)
    vs = VolatilityService(config)
    ss = StrategySelector(config)
    rs = RiskService(config)

    dir_res = ds.calculate_direction_score(bos_choch=80, vwap=80, ema=80)
    vol_res = vs.calculate_volatility_context(current_iv=0.15, daily_returns=[0.01]*10)
    regime = RegimeContext(as_of=datetime.now(timezone.utc))

    strat_res = ss.evaluate_strategies(dir_res, vol_res, regime)
    assert strat_res.recommended.strategy_name == "Bull Call Debit Spread"
    assert strat_res.recommended.fit_score > 60.0

    # Test Risk Sizing Grade A+
    risk_res = rs.calculate_grade_and_risk(
        overall_score=92.0,
        account_equity=100000.0,
        max_loss_per_contract=250.0
    )
    assert risk_res.grade == "A+"
    assert risk_res.risk_pct_applied == 0.01
    assert risk_res.allowed_risk_dollars == 1000.0
    assert risk_res.contracts_allowed == 4
    assert risk_res.is_trade_approved is True
