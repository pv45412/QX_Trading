"""SignalService pipeline orchestrator for QX Options Scanner V1.

Executes the full 7-gate options scan pipeline for a ticker:
Gate 1: Hard Veto Checks
Gate 2: Direction Composite Engine (0..100)
Gate 3: Volatility Engine & EWMA RV (0..100)
Gate 4: Market Regime Engine
Gate 5: Strategy Selector
Gate 6: Trade Constructor (Strike, Expiration, Debit/Credit, Risk/Reward)
Gate 7: Risk Sizing Service (Grade A+, A, B sizing floor)
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.models import UnderlyingQuote, OptionChain, RegimeContext, ScanResult
from qx.options_scanner.services.veto_service import VetoService
from qx.options_scanner.services.direction_service import DirectionService
from qx.options_scanner.services.volatility_service import VolatilityService
from qx.options_scanner.services.strategy_selector import StrategySelector
from qx.options_scanner.services.trade_constructor import TradeConstructor
from qx.options_scanner.services.risk_service import RiskService


class SignalService:
    def __init__(self, config: Optional[ScannerConfig] = None):
        self.config = config or ScannerConfig()
        self.veto_service = VetoService(self.config)
        self.direction_service = DirectionService(self.config)
        self.volatility_service = VolatilityService(self.config)
        self.strategy_selector = StrategySelector(self.config)
        self.trade_constructor = TradeConstructor(self.config)
        self.risk_service = RiskService(self.config)

    def scan_ticker(
        self,
        quote: UnderlyingQuote,
        chain: OptionChain,
        regime: Optional[RegimeContext] = None,
        daily_returns: Optional[List[float]] = None,
        account_equity: float = 100000.0,
        current_iv: float = 0.25,
        bos_choch: float = 50.0,
        vwap: float = 50.0,
        ema: float = 50.0,
        rvol: float = 50.0,
        cum_delta: float = 50.0,
        fvg: float = 50.0,
        rs: float = 50.0,
        iv_rank: float = 50.0,
        skew_25d: float = 50.0,
        term_struct: float = 50.0,
        em_fit: float = 50.0
    ) -> ScanResult:
        now = quote.timestamp or datetime.utcnow()
        if regime is None:
            regime = RegimeContext(as_of=now)

        # Gate 1: Hard Veto Checks
        veto_res = self.veto_service.evaluate_vetoes(quote, chain)
        if not veto_res.passed:
            return ScanResult(
                symbol=quote.symbol,
                timestamp=now,
                config_version=self.config.config_version,
                passed_veto=False,
                veto_result=veto_res,
                overall_score=0.0
            )

        # Gate 2: Direction Composite Engine
        dir_res = self.direction_service.calculate_direction_score(
            bos_choch=bos_choch,
            vwap=vwap,
            ema=ema,
            rvol=rvol,
            cum_delta=cum_delta,
            fvg=fvg,
            rs=rs
        )

        # Gate 3: Volatility Engine & EWMA RV Proxy
        returns = daily_returns or []
        vol_res = self.volatility_service.calculate_volatility_context(
            current_iv=current_iv,
            daily_returns=returns,
            iv_rank=iv_rank,
            skew_25d_score=skew_25d,
            term_structure_score=term_struct,
            expected_move_fit_score=em_fit
        )

        # Overall continuous score (50% direction fit, 50% volatility setup fit)
        overall_score = round(0.5 * dir_res.score + 0.5 * vol_res.score, 2)

        # Gate 5: Strategy Selector
        strat_res = self.strategy_selector.evaluate_strategies(
            direction=dir_res,
            volatility=vol_res,
            regime=regime
        )

        # Gate 6: Trade Constructor
        trade = self.trade_constructor.construct_trade(
            quote=quote,
            chain=chain,
            strategy=strat_res.recommended
        )

        # Gate 7: Risk Sizing Service
        max_loss = trade.max_loss_per_contract if trade else 0.0
        risk_res = self.risk_service.calculate_grade_and_risk(
            overall_score=overall_score,
            account_equity=account_equity,
            max_loss_per_contract=max_loss
        )

        return ScanResult(
            symbol=quote.symbol,
            timestamp=now,
            config_version=self.config.config_version,
            passed_veto=True,
            veto_result=veto_res,
            overall_score=overall_score,
            direction_result=dir_res,
            volatility_result=vol_res,
            strategy_result=strat_res,
            trade=trade,
            risk_result=risk_res
        )
