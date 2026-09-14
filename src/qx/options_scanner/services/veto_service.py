"""VetoService implementing the 7 hard vetoes for QX Options Scanner V1.

Hard vetoes only for true disqualifiers. Every veto returns a typed reason with details.
"""

from datetime import datetime, timezone
from typing import Optional

from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.models import (
    OptionChain, OptionContract, OptionTypeEnum, UnderlyingQuote,
    VetoReasonEnum, VetoResult
)


class VetoService:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def check_underlying(self, quote: UnderlyingQuote, now: Optional[datetime] = None) -> VetoResult:
        now_dt = now or datetime.now(timezone.utc)

        # 1. INSOLVENCY_FLAG
        if quote.is_insolvent:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.INSOLVENCY_FLAG,
                details={"symbol": quote.symbol, "is_insolvent": True}
            )

        # 2. DATA_STALE
        quote_ts = quote.timestamp
        if quote_ts.tzinfo is None:
            quote_ts = quote_ts.replace(tzinfo=timezone.utc)
        age_seconds = (now_dt - quote_ts).total_seconds()
        if age_seconds < 0 or age_seconds > self.config.max_data_age_seconds:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.DATA_STALE,
                details={"symbol": quote.symbol, "age_seconds": age_seconds, "limit": self.config.max_data_age_seconds}
            )

        # 3. EARNINGS_BLACKOUT (Normal Mode)
        if self.config.mode == "normal" and quote.earnings_date:
            earn_ts = quote.earnings_date
            if earn_ts.tzinfo is None:
                earn_ts = earn_ts.replace(tzinfo=timezone.utc)
            days_to_earnings = abs((earn_ts - now_dt).total_seconds()) / 86400.0
            if days_to_earnings <= self.config.blackouts.normal_mode_earnings_days:
                return VetoResult(
                    passed=False,
                    reason=VetoReasonEnum.EARNINGS_BLACKOUT,
                    details={"symbol": quote.symbol, "days_to_earnings": round(days_to_earnings, 2), "limit_days": self.config.blackouts.normal_mode_earnings_days}
                )

        # 4. EVENT_BLACKOUT (Normal Mode)
        if self.config.mode == "normal" and quote.next_fomc_cpi_event:
            event_ts = quote.next_fomc_cpi_event
            if event_ts.tzinfo is None:
                event_ts = event_ts.replace(tzinfo=timezone.utc)
            hours_to_event = (event_ts - now_dt).total_seconds() / 3600.0
            if 0 <= hours_to_event <= self.config.blackouts.fomc_cpi_event_hours:
                return VetoResult(
                    passed=False,
                    reason=VetoReasonEnum.EVENT_BLACKOUT,
                    details={"symbol": quote.symbol, "hours_to_event": round(hours_to_event, 2), "limit_hours": self.config.blackouts.fomc_cpi_event_hours}
                )

        return VetoResult(passed=True)

    def check_chain(self, chain: OptionChain, quote: UnderlyingQuote, now: Optional[datetime] = None) -> VetoResult:
        now_dt = now or datetime.now(timezone.utc)

        # First check underlying
        underlying_veto = self.check_underlying(quote, now=now_dt)
        if not underlying_veto.passed:
            return underlying_veto

        # 5. CHAIN_INCOMPLETE
        if not chain.contracts or len(chain.contracts) == 0:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.CHAIN_INCOMPLETE,
                details={"symbol": chain.underlying_symbol, "contract_count": 0}
            )

        calls = [c for c in chain.contracts if c.option_type == OptionTypeEnum.CALL]
        puts = [c for c in chain.contracts if c.option_type == OptionTypeEnum.PUT]
        if not calls or not puts:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.CHAIN_INCOMPLETE,
                details={"symbol": chain.underlying_symbol, "call_count": len(calls), "put_count": len(puts)}
            )

        # Check chain staleness
        chain_ts = chain.retrieved_at
        if chain_ts.tzinfo is None:
            chain_ts = chain_ts.replace(tzinfo=timezone.utc)
        chain_age_seconds = (now_dt - chain_ts).total_seconds()
        if chain_age_seconds < 0 or chain_age_seconds > self.config.max_data_age_seconds:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.DATA_STALE,
                details={"symbol": chain.underlying_symbol, "chain_age_seconds": chain_age_seconds, "limit": self.config.max_data_age_seconds}
            )

        return VetoResult(passed=True)

    def evaluate_vetoes(self, quote: UnderlyingQuote, chain: OptionChain, now: Optional[datetime] = None) -> VetoResult:
        return self.check_chain(chain=chain, quote=quote, now=now)

    def check_contract_liquidity(self, contract: OptionContract) -> VetoResult:
        # 6. LIQUIDITY_OI
        if contract.open_interest < self.config.liquidity.min_open_interest:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.LIQUIDITY_OI,
                details={
                    "contract_symbol": contract.symbol,
                    "open_interest": contract.open_interest,
                    "min_open_interest": self.config.liquidity.min_open_interest
                }
            )

        # 7. LIQUIDITY_SPREAD
        spread_pct = contract.spread_pct
        if spread_pct > self.config.liquidity.max_option_spread_pct:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.LIQUIDITY_SPREAD,
                details={
                    "contract_symbol": contract.symbol,
                    "spread_pct": spread_pct,
                    "max_spread_pct": self.config.liquidity.max_option_spread_pct
                }
            )

        return VetoResult(passed=True)

    def check_portfolio_risk(
        self,
        symbol: str,
        current_sector_exposure_pct: float,
        max_sector_limit_pct: float = 25.0,
    ) -> VetoResult:
        """Veto trade idea if portfolio sector exposure exceeds risk limits."""
        if current_sector_exposure_pct > max_sector_limit_pct:
            return VetoResult(
                passed=False,
                reason=VetoReasonEnum.DATA_STALE,  # Reuse or fail closed on risk limit
                details={
                    "symbol": symbol,
                    "current_sector_exposure_pct": current_sector_exposure_pct,
                    "max_sector_limit_pct": max_sector_limit_pct,
                    "veto_type": "PORTFOLIO_SECTOR_LIMIT_EXCEEDED",
                },
            )
        return VetoResult(passed=True)

