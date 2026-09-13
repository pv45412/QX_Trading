"""TradeConstructor service for QX Options Scanner V1.

Constructs trade leg parameters, target deltas, expiration dates, strikes, net debit/credit,
max profit/loss, breakeven levels, entry/invalidation/targets, and R ratio.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.models import OptionChain, OptionContract, OptionTypeEnum, UnderlyingQuote
from qx.options_scanner.services.strategy_selector import StrategyFit


class TradeLeg(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_symbol: str
    action: str  # BUY | SELL
    option_type: OptionTypeEnum
    strike: float
    expiration: str
    dte: int
    delta: float
    bid: float
    ask: float
    mid: float


class ConstructedTrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    underlying_symbol: str
    underlying_price: float
    strategy_name: str
    expiration: str
    dte: int
    legs: List[TradeLeg]
    net_debit_credit: float = Field(description="Positive for Debit, Negative for Credit")
    spread_width: float
    max_profit_per_contract: float
    max_loss_per_contract: float
    breakeven_price: float
    entry_price: float
    invalidation_stop: float
    target_price_1: float
    target_price_2: float
    risk_reward_ratio: float


class TradeConstructor:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def find_best_strike(self, contracts: List[OptionContract], target_delta: float) -> Optional[OptionContract]:
        if not contracts:
            return None
        return min(contracts, key=lambda c: abs(abs(c.delta) - target_delta))

    def construct_trade(
        self,
        quote: UnderlyingQuote,
        chain: OptionChain,
        strategy: StrategyFit,
        mode: str = "swing"
    ) -> Optional[ConstructedTrade]:
        contracts = chain.contracts
        if not contracts:
            return None

        price = quote.last_price
        target_deltas = self.config.deltas

        # Select contracts for strategy
        calls = [c for c in contracts if c.option_type == OptionTypeEnum.CALL]
        puts = [c for c in contracts if c.option_type == OptionTypeEnum.PUT]

        if strategy.strategy_name in ("Bull Call Debit Spread", "Long Call"):
            if not calls:
                return None
            long_call = self.find_best_strike(calls, target_deltas.debit_long_delta)
            if not long_call:
                return None

            if strategy.strategy_name == "Long Call":
                net_cost = long_call.mid_price * 100.0
                max_loss = net_cost
                max_profit = net_cost * 2.5
                breakeven = round(long_call.strike + long_call.mid_price, 2)
                legs = [
                    TradeLeg(
                        contract_symbol=long_call.symbol,
                        action="BUY",
                        option_type=OptionTypeEnum.CALL,
                        strike=long_call.strike,
                        expiration=long_call.expiration,
                        dte=long_call.dte,
                        delta=long_call.delta,
                        bid=long_call.bid,
                        ask=long_call.ask,
                        mid=long_call.mid_price
                    )
                ]
                return ConstructedTrade(
                    underlying_symbol=quote.symbol,
                    underlying_price=price,
                    strategy_name="Long Call",
                    expiration=long_call.expiration,
                    dte=long_call.dte,
                    legs=legs,
                    net_debit_credit=round(long_call.mid_price, 2),
                    spread_width=0.0,
                    max_profit_per_contract=round(max_profit, 2),
                    max_loss_per_contract=round(max_loss, 2),
                    breakeven_price=breakeven,
                    entry_price=round(price * 1.001, 2),
                    invalidation_stop=round(price * 0.992, 2),
                    target_price_1=round(price * 1.015, 2),
                    target_price_2=round(price * 1.030, 2),
                    risk_reward_ratio=2.5
                )

            # Bull Call Debit Spread
            short_calls = [c for c in calls if c.strike > long_call.strike]
            short_call = self.find_best_strike(short_calls, target_deltas.debit_short_delta) if short_calls else None
            if not short_call:
                return None

            width = round(short_call.strike - long_call.strike, 2)
            net_debit = round(long_call.mid_price - short_call.mid_price, 2)
            if net_debit <= 0:
                net_debit = 0.10

            max_loss = net_debit * 100.0
            max_profit = (width - net_debit) * 100.0
            breakeven = round(long_call.strike + net_debit, 2)

            legs = [
                TradeLeg(contract_symbol=long_call.symbol, action="BUY", option_type=OptionTypeEnum.CALL, strike=long_call.strike, expiration=long_call.expiration, dte=long_call.dte, delta=long_call.delta, bid=long_call.bid, ask=long_call.ask, mid=long_call.mid_price),
                TradeLeg(contract_symbol=short_call.symbol, action="SELL", option_type=OptionTypeEnum.CALL, strike=short_call.strike, expiration=short_call.expiration, dte=short_call.dte, delta=short_call.delta, bid=short_call.bid, ask=short_call.ask, mid=short_call.mid_price)
            ]

            return ConstructedTrade(
                underlying_symbol=quote.symbol,
                underlying_price=price,
                strategy_name="Bull Call Debit Spread",
                expiration=long_call.expiration,
                dte=long_call.dte,
                legs=legs,
                net_debit_credit=net_debit,
                spread_width=width,
                max_profit_per_contract=round(max_profit, 2),
                max_loss_per_contract=round(max_loss, 2),
                breakeven_price=breakeven,
                entry_price=round(price * 1.001, 2),
                invalidation_stop=round(price * 0.992, 2),
                target_price_1=round(price * 1.015, 2),
                target_price_2=round(price * 1.030, 2),
                risk_reward_ratio=round(max_profit / max(1.0, max_loss), 2)
            )

        # Fallback default trade layout for other strategies
        if not puts:
            return None
        short_put = self.find_best_strike(puts, target_deltas.credit_short_delta)
        if not short_put:
            return None
        
        long_puts = [p for p in puts if p.strike < short_put.strike]
        long_put = self.find_best_strike(long_puts, 0.10) if long_puts else short_put

        width = round(abs(short_put.strike - long_put.strike), 2) or 5.0
        net_credit = round(short_put.mid_price - long_put.mid_price, 2)
        if net_credit <= 0:
            net_credit = 0.50

        max_profit = net_credit * 100.0
        max_loss = (width - net_credit) * 100.0
        breakeven = round(short_put.strike - net_credit, 2)

        legs = [
            TradeLeg(contract_symbol=short_put.symbol, action="SELL", option_type=OptionTypeEnum.PUT, strike=short_put.strike, expiration=short_put.expiration, dte=short_put.dte, delta=short_put.delta, bid=short_put.bid, ask=short_put.ask, mid=short_put.mid_price),
            TradeLeg(contract_symbol=long_put.symbol, action="BUY", option_type=OptionTypeEnum.PUT, strike=long_put.strike, expiration=long_put.expiration, dte=long_put.dte, delta=long_put.delta, bid=long_put.bid, ask=long_put.ask, mid=long_put.mid_price)
        ]

        return ConstructedTrade(
            underlying_symbol=quote.symbol,
            underlying_price=price,
            strategy_name=strategy.strategy_name,
            expiration=short_put.expiration,
            dte=short_put.dte,
            legs=legs,
            net_debit_credit=-net_credit,
            spread_width=width,
            max_profit_per_contract=round(max_profit, 2),
            max_loss_per_contract=round(max_loss, 2),
            breakeven_price=breakeven,
            entry_price=round(price * 0.999, 2),
            invalidation_stop=round(price * 0.990, 2),
            target_price_1=round(price * 1.010, 2),
            target_price_2=round(price * 1.020, 2),
            risk_reward_ratio=round(max_profit / max(1.0, max_loss), 2)
        )
