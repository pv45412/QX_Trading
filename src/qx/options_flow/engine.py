from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from qx.options_flow.classify_flow import classify_trade
from qx.options_flow.contract_selector import select_contracts
from qx.options_flow.direction_score import score_direction
from qx.options_flow.iv_quality import evaluate_iv_quality
from qx.options_flow.models import (
    FlowClassification,
    MarketRegimeContext,
    OptionFlowAnalysis,
    OptionFlowTrade,
    UnderlyingContext,
)
from qx.options_flow.premium_scoring import analyze_premium
from qx.options_flow.price_confirmation import confirm_price
from qx.options_flow.risk_filter import assess_no_trade_risk


CSV_ALIASES = {
    "ticker": {"ticker", "symbol", "underlying"},
    "option_symbol": {"option_symbol", "contract", "contract_symbol", "option"},
    "expiration": {"expiration", "expiry", "exp"},
    "strike": {"strike"},
    "option_type": {"call_put", "option_type", "type", "put_call", "cp"},
    "trade_price": {"trade_price", "price", "last", "fill_price"},
    "bid": {"bid"},
    "ask": {"ask"},
    "size": {"size", "qty", "quantity", "contracts"},
    "premium": {"premium", "notional", "cost"},
    "volume": {"volume", "vol"},
    "open_interest": {"open_interest", "oi", "openint"},
    "implied_volatility": {"implied_volatility", "iv", "imp_vol"},
    "delta": {"delta"},
    "gamma": {"gamma"},
    "trade_condition": {"trade_condition", "condition", "conditions"},
    "trade_kind": {"trade_kind", "kind", "sweep_block", "type_detail"},
    "timestamp": {"timestamp", "time", "date_time", "datetime"},
}


def analyze_option_flow(
    trades: list[OptionFlowTrade],
    *,
    underlying: UnderlyingContext,
    regime: MarketRegimeContext | None = None,
    event_risk: bool = False,
) -> OptionFlowAnalysis:
    resolved_regime = regime or MarketRegimeContext()
    classifications = [classify_trade(trade) for trade in trades]
    premium = analyze_premium(trades, classifications)
    iv_quality = evaluate_iv_quality(trades, event_risk=event_risk or resolved_regime.macro_event_risk)
    price = confirm_price(underlying)
    risk = assess_no_trade_risk(trades, classifications, iv_quality, price, resolved_regime)
    direction = score_direction(classifications, premium, iv_quality, price, resolved_regime, risk)
    return OptionFlowAnalysis(
        ticker=underlying.ticker,
        current_price=underlying.current_price,
        call_buy_score=direction.call_buy_score,
        put_buy_score=direction.put_buy_score,
        no_trade_risk=direction.no_trade_risk,
        final_signal=direction.final_signal,
        trigger_price=price.trigger_price,
        invalidation_price=price.invalidation_price,
        why=direction.why,
        warnings=direction.warnings,
        trades=trades,
        classifications=classifications,
        suggested_contracts=select_contracts(trades, current_price=underlying.current_price),
    )


def parse_flow_csv(frame: pd.DataFrame, *, default_ticker: str) -> list[OptionFlowTrade]:
    if frame.empty:
        return []
    normalized = frame.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in normalized.columns]
    column_map = _column_map(normalized)
    trades: list[OptionFlowTrade] = []
    for row in normalized.to_dict(orient="records"):
        data: dict[str, Any] = {}
        for target, source in column_map.items():
            data[target] = row.get(source)
        data.setdefault("ticker", default_ticker)
        if not str(data.get("ticker") or "").strip():
            data["ticker"] = default_ticker
        data = _coerce_trade_data(data)
        trades.append(OptionFlowTrade.model_validate(data))
    return trades


def trades_frame(
    trades: list[OptionFlowTrade],
    classifications: list[FlowClassification],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for trade, classification in zip(trades, classifications, strict=True):
        rows.append(
            {
                "ticker": trade.ticker,
                "option_symbol": trade.option_symbol,
                "expiration": trade.expiration,
                "strike": trade.strike,
                "option_type": trade.option_type,
                "trade_price": trade.trade_price,
                "bid": trade.bid,
                "ask": trade.ask,
                "spread_pct": trade.spread_pct,
                "size": trade.size,
                "premium": trade.effective_premium,
                "volume": trade.volume,
                "open_interest": trade.open_interest,
                "implied_volatility": trade.implied_volatility,
                "delta": trade.delta,
                "trade_kind": trade.trade_kind,
                "trade_side": classification.trade_side,
                "directional_read": classification.directional_read,
                "aggression_score": classification.aggression_score,
                "risk_tags": ", ".join(classification.risk_tags),
            }
        )
    return pd.DataFrame(rows)


def suggested_contracts_frame(analysis: OptionFlowAnalysis) -> pd.DataFrame:
    return pd.DataFrame([contract.model_dump() for contract in analysis.suggested_contracts])


def _column_map(frame: pd.DataFrame) -> dict[str, str]:
    columns = set(frame.columns)
    mapping: dict[str, str] = {}
    for target, aliases in CSV_ALIASES.items():
        match = next((alias for alias in aliases if alias in columns), None)
        if match is not None:
            mapping[target] = match
    return mapping


def _coerce_trade_data(data: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(data)
    for key in [
        "strike",
        "trade_price",
        "bid",
        "ask",
        "premium",
        "implied_volatility",
        "delta",
        "gamma",
    ]:
        coerced[key] = _float(coerced.get(key))
    for key in ["size", "volume", "open_interest"]:
        coerced[key] = int(_float(coerced.get(key)))
    if coerced.get("expiration") not in {None, ""}:
        coerced["expiration"] = _date(coerced["expiration"])
    if coerced.get("timestamp") not in {None, ""}:
        coerced["timestamp"] = _datetime(coerced["timestamp"])
    return coerced


def _float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, float) and pd.isna(value):
        return 0.0
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    if text == "":
        return 0.0
    parsed = float(text)
    return parsed / 100 if "%" in str(value) else parsed


def _date(value: object) -> date | None:
    try:
        return pd.Timestamp(str(value)).date()
    except Exception:
        return None


def _datetime(value: object) -> datetime | None:
    try:
        return pd.Timestamp(str(value)).to_pydatetime()
    except Exception:
        return None
