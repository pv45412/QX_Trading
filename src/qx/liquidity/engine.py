from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import isfinite
from typing import Any, cast

import pandas as pd

from qx.data.providers import MarketDataProvider
from qx.liquidity.models import LiquidityLevel, LiquiditySnapshot, OptionWall
from qx.models.market import BarDataRequest
from qx.options.chains import OptionContract, OptionsChainProvider


FUTURES_SYMBOL_MAP = {
    "/ES": "ES=F",
    "ES": "ES=F",
    "/NQ": "NQ=F",
    "NQ": "NQ=F",
    "/RTY": "RTY=F",
    "RTY": "RTY=F",
    "/CL": "CL=F",
    "CL": "CL=F",
    "/GC": "GC=F",
    "GC": "GC=F",
}


def build_liquidity_map(
    symbol: str,
    provider: MarketDataProvider,
    *,
    options_provider: OptionsChainProvider | None = None,
    period: str = "6mo",
) -> LiquiditySnapshot:
    requested_symbol = symbol.strip().upper()
    data_symbol = normalize_data_symbol(requested_symbol)
    bars = provider.get_daily_bars(BarDataRequest(symbol=data_symbol, period=period))
    if len(bars) < 21:
        raise ValueError(f"{requested_symbol} needs at least 21 daily bars, got {len(bars)}")

    current_price = round(float(bars["close"].iloc[-1]), 2)
    levels = build_price_structure_levels(requested_symbol, data_symbol, bars)
    diagnostics: list[str] = []
    option_walls: list[OptionWall] = []
    if options_provider is None or requested_symbol.startswith("/") or data_symbol.endswith("=F"):
        diagnostics.append("Options walls unavailable for this symbol/data source.")
    else:
        try:
            option_walls = build_option_walls(requested_symbol, current_price, options_provider)
            levels.extend(_levels_from_option_walls(requested_symbol, current_price, option_walls))
        except Exception as exc:
            diagnostics.append(f"Options walls unavailable: {exc}")

    levels = _dedupe_levels(levels)
    support = _nearest_level(levels, side="support", current_price=current_price)
    resistance = _nearest_level(levels, side="resistance", current_price=current_price)
    call_wall = next((wall for wall in option_walls if wall.side == "call"), None)
    put_wall = next((wall for wall in option_walls if wall.side == "put"), None)

    return LiquiditySnapshot(
        symbol=requested_symbol,
        data_symbol=data_symbol,
        asset_type=_asset_type(requested_symbol, data_symbol),
        current_price=current_price,
        bias=_bias(current_price, support, resistance),
        nearest_support=support,
        nearest_resistance=resistance,
        top_call_wall=call_wall,
        top_put_wall=put_wall,
        levels=levels,
        option_walls=option_walls,
        diagnostics=diagnostics,
    )


def normalize_data_symbol(symbol: str) -> str:
    return FUTURES_SYMBOL_MAP.get(symbol.upper(), symbol.upper())


def build_price_structure_levels(
    requested_symbol: str,
    data_symbol: str,
    bars: pd.DataFrame,
) -> list[LiquidityLevel]:
    current = float(bars["close"].iloc[-1])
    prior = bars.iloc[-2]
    candidates: list[tuple[float, str, str, str, float]] = [
        (float(prior["high"]), "Prior High", "resistance", "price", 0.88),
        (float(prior["low"]), "Prior Low", "support", "price", 0.88),
        (float(prior["close"]), "Prior Close", _side_for_level(float(prior["close"]), current), "price", 0.55),
    ]
    for window, label, weight in [(5, "5D", 0.70), (20, "20D", 0.78), (60, "60D", 0.72)]:
        if len(bars) >= window:
            window_bars = bars.tail(window)
            candidates.append((float(window_bars["high"].max()), f"{label} High", "resistance", "structure", weight))
            candidates.append((float(window_bars["low"].min()), f"{label} Low", "support", "structure", weight))

    candidates.extend(_round_number_candidates(current))
    candidates.extend(_pivot_candidates(bars, current, max_levels=10))

    return [
        _level_from_candidate(requested_symbol, current, price, label, side, source, weight)
        for price, label, side, source, weight in candidates
        if price > 0 and isfinite(price)
    ]


def build_option_walls(
    symbol: str,
    current_price: float,
    provider: OptionsChainProvider,
    *,
    max_dte: int = 120,
) -> list[OptionWall]:
    calls = [contract for contract in provider.get_calls(symbol) if contract.dte <= max_dte]
    puts = [contract for contract in provider.get_puts(symbol) if contract.dte <= max_dte]
    walls = _aggregate_walls(symbol, current_price, calls, side="call")
    walls.extend(_aggregate_walls(symbol, current_price, puts, side="put"))
    walls.sort(key=lambda wall: wall.score, reverse=True)
    return walls[:12]


def liquidity_levels_frame(levels: list[LiquidityLevel]) -> pd.DataFrame:
    return pd.DataFrame([level.__dict__ for level in levels])


def option_walls_frame(walls: list[OptionWall]) -> pd.DataFrame:
    return pd.DataFrame([wall.__dict__ for wall in walls])


def generate_tos_liquidity_study(snapshot: LiquiditySnapshot, *, max_levels: int = 8) -> str:
    levels = sorted(snapshot.levels, key=lambda level: level.score, reverse=True)[:max_levels]
    lines = [
        "# QX Liquidity Map Levels",
        f"# Generated for {snapshot.symbol} from local SCANNER",
        "declare upper;",
        "",
    ]
    for index, level in enumerate(levels, start=1):
        name = f"QX_Level_{index}"
        lines.append(f"plot {name} = {level.price:.2f};")
        lines.append(
            f'{name}.SetDefaultColor({"Color.GREEN" if level.side == "support" else "Color.RED"});'
        )
        lines.append(f"{name}.SetStyle(Curve.SHORT_DASH);")
        lines.append(f'{name}.SetLineWeight({3 if level.score >= 0.85 else 2});')
        lines.append("")
    lines.append(
        f'AddLabel(yes, "QX Liquidity: {snapshot.bias} | {snapshot.current_price:.2f}", Color.WHITE);'
    )
    return "\n".join(lines)


def _aggregate_walls(
    symbol: str,
    current_price: float,
    contracts: list[OptionContract],
    *,
    side: str,
) -> list[OptionWall]:
    grouped: dict[tuple[date, float], list[OptionContract]] = defaultdict(list)
    for contract in contracts:
        if contract.open_interest > 0 or contract.volume > 0:
            grouped[(contract.expiration, contract.strike)].append(contract)

    max_interest = max((sum(contract.open_interest for contract in items) for items in grouped.values()), default=1)
    max_volume = max((sum(contract.volume for contract in items) for items in grouped.values()), default=1)
    walls: list[OptionWall] = []
    for (expiration, strike), items in grouped.items():
        open_interest = sum(contract.open_interest for contract in items)
        volume = sum(contract.volume for contract in items)
        iv = sum(contract.implied_volatility for contract in items) / len(items)
        distance = (strike / current_price) - 1.0 if current_price > 0 else 0.0
        distance_score = max(0.0, 1.0 - min(abs(distance) / 0.12, 1.0))
        interest_score = open_interest / max_interest if max_interest else 0.0
        volume_score = volume / max_volume if max_volume else 0.0
        score = _clamp(interest_score * 0.55 + volume_score * 0.30 + distance_score * 0.15)
        walls.append(
            OptionWall(
                symbol=symbol,
                expiration=expiration.isoformat(),
                strike=round(strike, 2),
                side=side,
                open_interest=open_interest,
                volume=volume,
                implied_volatility=round(iv, 4),
                score=round(score, 3),
                distance_pct=round(distance, 4),
            )
        )
    walls.sort(key=lambda wall: wall.score, reverse=True)
    return walls[:6]


def _levels_from_option_walls(
    symbol: str,
    current_price: float,
    walls: list[OptionWall],
) -> list[LiquidityLevel]:
    levels: list[LiquidityLevel] = []
    for wall in walls[:8]:
        side = _side_for_level(wall.strike, current_price)
        label = f"{wall.side.title()} Wall {wall.expiration}"
        weight = 0.82 if wall.score >= 0.75 else 0.68
        levels.append(_level_from_candidate(symbol, current_price, wall.strike, label, side, "options", weight))
    return levels


def _round_number_candidates(current: float) -> list[tuple[float, str, str, str, float]]:
    step = _round_step(current)
    base = round(current / step) * step
    levels: list[tuple[float, str, str, str, float]] = []
    for offset in range(-3, 4):
        price = base + offset * step
        if price > 0:
            levels.append((price, f"Round {step:g}", _side_for_level(price, current), "round", 0.42))
    return levels


def _pivot_candidates(
    bars: pd.DataFrame,
    current: float,
    *,
    max_levels: int,
) -> list[tuple[float, str, str, str, float]]:
    window = bars.tail(80).reset_index(drop=True)
    pivots: list[tuple[float, str, str, str, float]] = []
    for index in range(2, len(window) - 2):
        high = _frame_float(window, index, "high")
        low = _frame_float(window, index, "low")
        nearby_highs = [_frame_float(window, index + offset, "high") for offset in (-2, -1, 1, 2)]
        nearby_lows = [_frame_float(window, index + offset, "low") for offset in (-2, -1, 1, 2)]
        recency = index / max(len(window) - 1, 1)
        if high >= max(nearby_highs):
            pivots.append((high, "Pivot High", "resistance", "pivot", 0.50 + recency * 0.20))
        if low <= min(nearby_lows):
            pivots.append((low, "Pivot Low", "support", "pivot", 0.50 + recency * 0.20))
    pivots.sort(key=lambda item: (abs((item[0] / current) - 1.0), -item[4]))
    return pivots[:max_levels]


def _level_from_candidate(
    symbol: str,
    current: float,
    price: float,
    label: str,
    side: str,
    source: str,
    weight: float,
) -> LiquidityLevel:
    distance = (price / current) - 1.0 if current > 0 else 0.0
    distance_score = max(0.0, 1.0 - min(abs(distance) / 0.10, 1.0))
    score = _clamp(weight * 0.70 + distance_score * 0.30)
    note = _level_note(label, side, distance)
    return LiquidityLevel(
        symbol=symbol,
        price=round(price, 2),
        label=label,
        side=side,
        source=source,
        score=round(score, 3),
        distance_pct=round(distance, 4),
        note=note,
    )


def _frame_float(frame: pd.DataFrame, row: int, column: str) -> float:
    value = cast(Any, frame.at[row, column])
    if isinstance(value, date):
        return 0.0
    return float(value)


def _dedupe_levels(levels: list[LiquidityLevel]) -> list[LiquidityLevel]:
    deduped: dict[tuple[float, str], LiquidityLevel] = {}
    for level in levels:
        key = (round(level.price, 2), level.side)
        existing = deduped.get(key)
        if existing is None or level.score > existing.score:
            deduped[key] = level
    return sorted(deduped.values(), key=lambda level: (abs(level.distance_pct), -level.score))


def _nearest_level(
    levels: list[LiquidityLevel],
    *,
    side: str,
    current_price: float,
) -> LiquidityLevel | None:
    filtered = [
        level
        for level in levels
        if level.side == side
        and ((side == "support" and level.price <= current_price) or (side == "resistance" and level.price >= current_price))
    ]
    if not filtered:
        return None
    return sorted(filtered, key=lambda level: (abs(level.distance_pct), -level.score))[0]


def _side_for_level(price: float, current: float) -> str:
    return "resistance" if price >= current else "support"


def _level_note(label: str, side: str, distance: float) -> str:
    action = "buyers defend" if side == "support" else "sellers may defend"
    if abs(distance) <= 0.005:
        return f"{label} is active now; watch acceptance/rejection."
    return f"{action} near this {label.lower()} ({distance:+.1%})."


def _round_step(current: float) -> float:
    if current >= 1000:
        return 25.0
    if current >= 250:
        return 10.0
    if current >= 100:
        return 5.0
    if current >= 25:
        return 2.5
    return 1.0


def _asset_type(requested_symbol: str, data_symbol: str) -> str:
    if requested_symbol.startswith("/") or data_symbol.endswith("=F"):
        return "Future"
    if requested_symbol.startswith("^"):
        return "Index"
    if requested_symbol in {"SPY", "QQQ", "IWM", "DIA"}:
        return "ETF"
    return "Equity"


def _bias(
    current_price: float,
    support: LiquidityLevel | None,
    resistance: LiquidityLevel | None,
) -> str:
    if resistance and abs(resistance.distance_pct) <= 0.005:
        return "Testing Supply"
    if support and abs(support.distance_pct) <= 0.005:
        return "Testing Demand"
    if support and resistance:
        span = resistance.price - support.price
        if span > 0:
            position = (current_price - support.price) / span
            if position >= 0.70:
                return "Upper Range"
            if position <= 0.30:
                return "Lower Range"
    return "Balanced"


def _clamp(value: float) -> float:
    return max(0.0, min(value, 1.0))
