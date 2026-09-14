"""Production Phase 3 Integration Pipeline for QX Platform.

Connects:
1. Real-Time Market Data
2. Signal Validator (BOS/CHoCH, RVOL, VWAP, FVG, Sector)
3. Verified Option Chain Evidence
4. Read-Only Portfolio Context (Cached ~30s)
5. Portfolio Risk Vetoes & Concentration Checks
6. Decoupled 4-Tier Trade Scorer (Signal / Fit / Risk / Final)
7. Account Equity Position Sizer
8. Dual Freshness Gate (Quote & Signal Timestamps)
9. Fail-Closed Publication Gate
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from qx.execution.models import OrderRequest, OrderStatus
from qx.options.chains import OptionContract
from qx.options_scanner.models import UnderlyingQuote, VetoResult
from qx.options_scanner.services.position_sizer import AccountEquityPositionSizer, PositionSizingResult
from qx.options_scanner.services.trade_scorer import DecoupledTradeScorer, TradeScoreBreakdown
from qx.options_scanner.services.veto_service import VetoService
from qx.portfolio.models import PortfolioPosition, PortfolioSnapshot
from qx.portfolio.read_only_service import ReadOnlyPortfolioService
from qx.signals.freshness import FreshnessChecker, FreshnessResult
from qx.signals.validator import SignalValidationResult, SignalValidator, ValidationStatus


@dataclass(frozen=True)
class PipelineExecutionProposal:
    symbol: str
    publication_state: str  # VERIFIED | SIMULATED | BLOCKED
    executable: bool
    evidence_reason: str
    signal_validation: SignalValidationResult
    score_breakdown: TradeScoreBreakdown
    position_sizing: Optional[PositionSizingResult]
    freshness: FreshnessResult
    veto_result: VetoResult
    order_request: Optional[OrderRequest] = None


class Phase3PipelineIntegrator:
    """Production Integrator assembling Phase 3 components into one fail-closed pipeline."""

    def __init__(
        self,
        portfolio_service: Optional[ReadOnlyPortfolioService] = None,
        validator: Optional[SignalValidator] = None,
        veto_service: Optional[VetoService] = None,
        scorer: Optional[DecoupledTradeScorer] = None,
        sizer: Optional[AccountEquityPositionSizer] = None,
        freshness_checker: Optional[FreshnessChecker] = None,
    ) -> None:
        from qx.options_scanner.config import ScannerConfig

        self.portfolio_service = portfolio_service or ReadOnlyPortfolioService()
        self.validator = validator or SignalValidator()
        self.veto_service = veto_service or VetoService(ScannerConfig())
        self.scorer = scorer or DecoupledTradeScorer()
        self.sizer = sizer or AccountEquityPositionSizer()
        self.freshness_checker = freshness_checker or FreshnessChecker()

    def evaluate_pipeline(
        self,
        symbol: str,
        trend_bias: str,
        quote: UnderlyingQuote,
        signal_timestamp: datetime,
        option_contracts: Optional[List[OptionContract]] = None,
        sector: str = "Technology",
        rvol: float = 1.5,
        vwap: Optional[float] = None,
        bos_confirmed: bool = False,
        fvg_present: bool = False,
        sector_rs: float = 0.0,
        stop_loss_price: Optional[float] = None,
        target_price: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> PipelineExecutionProposal:
        now_dt = now or datetime.now(timezone.utc)

        # 1. Evaluate dual timestamp freshness
        freshness_res = self.freshness_checker.check_dual_freshness(
            symbol=symbol,
            quote_timestamp=quote.timestamp,
            signal_timestamp=signal_timestamp,
            now=now_dt,
        )

        # 2. Multi-factor technical signal validation
        signal_res = self.validator.validate_signal(
            symbol=symbol,
            trend_bias=trend_bias,
            price=quote.last_price,
            rvol=rvol,
            vwap=vwap,
            bos_confirmed=bos_confirmed,
            fvg_present=fvg_present,
            sector_relative_strength=sector_rs,
        )

        # 3. Read cached portfolio snapshot
        portfolio_snap = self.portfolio_service.get_cached_snapshot(now=now_dt)

        # Calculate current sector exposure pct
        current_sector_pct = 0.0
        for sec_alloc in portfolio_snap.sector_allocations:
            if sec_alloc.sector.lower() == sector.lower():
                current_sector_pct = sec_alloc.allocation_pct
                break

        is_duplicate = any(p.symbol.upper() == symbol.upper() for p in portfolio_snap.positions)

        # 4. Portfolio risk veto evaluation
        veto_res = self.veto_service.check_portfolio_risk(
            symbol=symbol,
            current_sector_exposure_pct=current_sector_pct,
            proposed_addition_pct=3.0,  # Estimated 3% position impact
            max_sector_limit_pct=25.0,
            is_duplicate_open_trade=is_duplicate,
            portfolio_freshness_state=portfolio_snap.freshness_state,
        )

        # 5. Position sizing based strictly on Account Equity
        stop_price = stop_loss_price if stop_loss_price is not None else (quote.last_price * 0.95 if trend_bias.upper() == "BULLISH" else quote.last_price * 1.05)
        sizing_res = self.sizer.calculate_position_size(
            symbol=symbol,
            account_equity=portfolio_snap.account.account_equity,
            buying_power=portfolio_snap.account.buying_power,
            entry_price=quote.last_price,
            stop_loss_price=stop_price,
            unit_multiplier=100 if option_contracts else 1,
        )

        # 6. Decoupled 4-Tier Trade Scorer
        score_breakdown = self.scorer.calculate_score_breakdown(
            symbol=symbol,
            technical_signal_score=signal_res.composite_score,
            current_sector_exposure_pct=current_sector_pct,
            proposed_addition_pct=3.0,
            max_sector_limit_pct=25.0,
            defined_risk_per_trade=sizing_res.total_dollar_risk,
            max_allowable_risk=sizing_res.max_allowable_dollar_risk,
            veto_reason=veto_res.reason.value if not veto_res.passed else None,
        )

        # 7. Check option chain evidence verification
        has_verified_chain = option_contracts is not None and len(option_contracts) > 0 and all(c.ask > 0 for c in option_contracts)

        # 8. Publication Gate & Fail-Closed Execution Decision
        if not freshness_res.is_executable:
            pub_state = "BLOCKED"
            executable = False
            evidence_reason = f"Execution BLOCKED: {freshness_res.reason}"
        elif not veto_res.passed:
            pub_state = "BLOCKED"
            executable = False
            evidence_reason = f"Execution BLOCKED by Portfolio Veto: {veto_res.reason.value}"
        elif not has_verified_chain:
            pub_state = "SIMULATED"
            executable = False
            evidence_reason = "Option contracts are modeled/missing and not verified from a live option chain."
        elif signal_res.status != ValidationStatus.VALIDATED:
            pub_state = "BLOCKED"
            executable = False
            evidence_reason = f"Execution BLOCKED: Signal validation status is {signal_res.status.value}."
        elif sizing_res.recommended_units < 1 or not sizing_res.is_buying_power_sufficient:
            pub_state = "BLOCKED"
            executable = False
            evidence_reason = "Execution BLOCKED: Position sizing zero or insufficient buying power."
        else:
            pub_state = "VERIFIED"
            executable = True
            evidence_reason = "Verified market quotes, signal validation, verified option chain, and portfolio risk checks passed."

        order_req: Optional[OrderRequest] = None
        if executable and has_verified_chain:
            order_req = OrderRequest(
                symbol=symbol,
                quantity=float(sizing_res.recommended_units),
                order_type="LIMIT",
                side="BUY",
                limit_price=quote.last_price,
                publication_state="VERIFIED",
                executable=True,
            )

        return PipelineExecutionProposal(
            symbol=symbol,
            publication_state=pub_state,
            executable=executable,
            evidence_reason=evidence_reason,
            signal_validation=signal_res,
            score_breakdown=score_breakdown,
            position_sizing=sizing_res,
            freshness=freshness_res,
            veto_result=veto_res,
            order_request=order_req,
        )
