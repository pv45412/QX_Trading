from dataclasses import dataclass, field
from typing import Any
import pandas as pd
import numpy as np


@dataclass
class PositionInput:
    symbol: str
    position_type: str = "Long Shares"  # "Long Shares", "Short Shares", "Long Call", "Long Put", "Bull Call Spread", "Bear Put Spread"
    entry_price: float = 0.0
    quantity: float = 100.0
    target_price: float | None = None
    stop_loss: float | None = None
    cost_basis: float = 0.0
    current_price: float | None = None
    option_mark: float | None = None


@dataclass
class PositionResearchReport:
    symbol: str
    position_type: str
    current_price: float
    entry_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    action_verdict: str  # "HOLD", "TRIM / TAKE PROFIT", "CLOSE / EXIT", "ROLL / ADJUST"
    confidence_score: float  # e.g., 0.85
    verdict_summary: str
    positive_factors: list[str] = field(default_factory=list)
    negative_factors: list[str] = field(default_factory=list)
    adjusted_stop_loss: float = 0.0
    adjusted_target_price: float = 0.0
    technical_metrics: dict[str, Any] = field(default_factory=dict)
    risk_metrics: dict[str, Any] = field(default_factory=dict)
    ai_evidence_summary: str = ""


def _calculate_rsi(series: pd.Series, period: int = 14) -> float:
    if len(series) < period + 1:
        return 50.0
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    last_gain = float(gain.iloc[-1])
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return float(df["close"].std()) if len(df) > 1 else 1.0
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]
    return float(atr) if not pd.isna(atr) else 1.0


def evaluate_position(
    pos: PositionInput,
    bars: pd.DataFrame,
    ai_summary: str | None = None,
) -> PositionResearchReport:
    """Run multi-dimensional quantitative research on an open position to issue an actionable verdict."""
    if bars.empty or "close" not in bars.columns:
        raise ValueError("Price bars dataframe cannot be empty.")

    current_price = float(pos.current_price) if pos.current_price and pos.current_price > 0 else float(bars["close"].iloc[-1])
    entry_price = pos.entry_price if pos.entry_price > 0 else current_price
    quantity = pos.quantity if pos.quantity > 0 else 100.0
    is_short = "Short" in pos.position_type or "Bear" in pos.position_type

    # Calculate P&L
    if pos.option_mark and pos.option_mark > 0 and ("Call" in pos.position_type or "Put" in pos.position_type or "Spread" in pos.position_type):
        multiplier = 100.0 if quantity <= 10 else 1.0
        unrealized_pnl = (pos.option_mark - entry_price) * quantity * multiplier
        unrealized_pnl_pct = (pos.option_mark - entry_price) / entry_price if entry_price > 0 else 0.0
    elif is_short:
        unrealized_pnl = (entry_price - current_price) * quantity
        unrealized_pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0.0
    else:
        unrealized_pnl = (current_price - entry_price) * quantity
        unrealized_pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0

    # Technical Indicators
    closes = bars["close"]
    sma_20 = float(closes.rolling(min(20, len(closes))).mean().iloc[-1])
    sma_50 = float(closes.rolling(min(50, len(closes))).mean().iloc[-1])
    sma_200 = float(closes.rolling(min(200, len(closes))).mean().iloc[-1])
    rsi_14 = _calculate_rsi(closes, 14)
    atr_14 = _calculate_atr(bars, 14)

    # 52-week High/Low
    high_52w = float(bars["high"].max())
    low_52w = float(bars["low"].min())
    pct_from_high = (current_price - high_52w) / high_52w

    # Target & Stop defaults
    if not pos.stop_loss or pos.stop_loss <= 0:
        suggested_stop = current_price - (2.0 * atr_14) if not is_short else current_price + (2.0 * atr_14)
    else:
        suggested_stop = pos.stop_loss

    if not pos.target_price or pos.target_price <= 0:
        suggested_target = current_price + (3.5 * atr_14) if not is_short else current_price - (3.5 * atr_14)
    else:
        suggested_target = pos.target_price

    # Risk-Reward calculation
    risk_per_unit = abs(current_price - suggested_stop) if suggested_stop else atr_14 * 2.0
    reward_per_unit = abs(suggested_target - current_price) if suggested_target else atr_14 * 3.5
    rr_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 1.5

    pos_factors: list[str] = []
    neg_factors: list[str] = []
    score = 0  # Net score from -10 to +10

    # Trend evaluation
    if not is_short:
        if current_price > sma_20:
            pos_factors.append(f"Trading above 20-day SMA (${sma_20:.2f})")
            score += 2
        else:
            neg_factors.append(f"Broke below 20-day SMA (${sma_20:.2f})")
            score -= 2

        if current_price > sma_50:
            pos_factors.append(f"Short-term uptrend intact above 50-day SMA (${sma_50:.2f})")
            score += 2
        else:
            neg_factors.append(f"Trading below 50-day SMA (${sma_50:.2f})")
            score -= 2

        if current_price > sma_200:
            pos_factors.append(f"Long-term structural bull trend above 200-day SMA (${sma_200:.2f})")
            score += 1
        else:
            neg_factors.append(f"Trading below 200-day structural SMA (${sma_200:.2f})")
            score -= 2
    else:
        if current_price < sma_20:
            pos_factors.append(f"Short position aligned with downtrend below 20-day SMA (${sma_20:.2f})")
            score += 2
        else:
            neg_factors.append(f"Price rallying above short 20-day SMA (${sma_20:.2f})")
            score -= 2

    # Momentum (RSI) evaluation
    if 45 <= rsi_14 <= 65:
        pos_factors.append(f"RSI(14) neutral-bullish momentum ({rsi_14:.1f})")
        score += 1
    elif rsi_14 > 70:
        neg_factors.append(f"RSI(14) overbought momentum ({rsi_14:.1f}) - vulnerable to pullbacks")
        score -= 2
    elif rsi_14 < 30:
        if not is_short:
            neg_factors.append(f"RSI(14) oversold ({rsi_14:.1f}) - strong downside momentum")
            score -= 2
        else:
            pos_factors.append(f"RSI(14) oversold ({rsi_14:.1f}) - favors short position")
            score += 2

    # P&L and Stop/Target evaluation
    if pos.stop_loss and pos.stop_loss > 0:
        if not is_short and current_price <= pos.stop_loss:
            neg_factors.append(f"Stop-Loss BREACHED! Current price ${current_price:.2f} <= Stop ${pos.stop_loss:.2f}")
            score -= 8
        elif is_short and current_price >= pos.stop_loss:
            neg_factors.append(f"Short Stop-Loss BREACHED! Current price ${current_price:.2f} >= Stop ${pos.stop_loss:.2f}")
            score -= 8

    if pos.target_price and pos.target_price > 0:
        if not is_short and current_price >= pos.target_price * 0.98:
            pos_factors.append(f"Target Price reached/imminent (${current_price:.2f} vs Target ${pos.target_price:.2f})")
            score += 3
        elif is_short and current_price <= pos.target_price * 1.02:
            pos_factors.append(f"Short Target Price reached/imminent (${current_price:.2f} vs Target ${pos.target_price:.2f})")
            score += 3

    if unrealized_pnl_pct >= 0.20:
        pos_factors.append(f"Strong open profit gain (+{unrealized_pnl_pct:.1%})")
        score += 2
    elif unrealized_pnl_pct <= -0.12:
        neg_factors.append(f"Significant open drawdown (-{abs(unrealized_pnl_pct):.1%})")
        score -= 3

    # Decision Matrix Formulation
    if (pos.stop_loss and ((not is_short and current_price <= pos.stop_loss) or (is_short and current_price >= pos.stop_loss))) or score <= -4:
        action_verdict = "CLOSE / EXIT"
        confidence_score = min(0.95, 0.70 + abs(score) * 0.03)
        verdict_summary = f"Exit recommended. Position has breached risk parameters or broken key moving average support (Score: {score})."
    elif (pos.target_price and ((not is_short and current_price >= pos.target_price * 0.98) or (is_short and current_price <= pos.target_price * 1.02))) or (unrealized_pnl_pct >= 0.25 and rsi_14 > 68):
        action_verdict = "TRIM / TAKE PROFIT"
        confidence_score = 0.88
        verdict_summary = f"Profit target achieved or momentum extended. Recommended to trim 50-75% position to lock in gains."
    elif "Call" in pos.position_type or "Put" in pos.position_type or "Spread" in pos.position_type:
        if unrealized_pnl_pct < -0.15 and current_price > sma_50:
            action_verdict = "ROLL / ADJUST"
            confidence_score = 0.82
            verdict_summary = "Option position down on theta/vega but trend remains bullish. Consider rolling strike or expiration."
        elif score >= 1:
            action_verdict = "HOLD"
            confidence_score = min(0.92, 0.65 + score * 0.04)
            verdict_summary = f"Hold position. Technical trend and option risk parameters remain favorable (Score: +{score})."
        else:
            action_verdict = "TRIM / TAKE PROFIT"
            confidence_score = 0.75
            verdict_summary = "Mixed technical signals for derivative position. Scaling out recommended."
    else:
        if score >= 0:
            action_verdict = "HOLD"
            confidence_score = min(0.94, 0.60 + score * 0.05)
            verdict_summary = f"Hold position intact. Trend health is supportive with positive risk:reward (Score: +{score})."
        else:
            action_verdict = "TRIM / TAKE PROFIT"
            confidence_score = 0.72
            verdict_summary = f"Position weakness detected. Consider trimming position size (Score: {score})."

    tech_metrics = {
        "sma_20": round(sma_20, 2),
        "sma_50": round(sma_50, 2),
        "sma_200": round(sma_200, 2),
        "rsi_14": round(rsi_14, 1),
        "atr_14": round(atr_14, 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "pct_from_high": round(pct_from_high, 4),
    }

    risk_metrics = {
        "risk_reward_ratio": round(rr_ratio, 2),
        "distance_to_stop_pct": round(abs(current_price - suggested_stop) / current_price, 4),
        "distance_to_target_pct": round(abs(suggested_target - current_price) / current_price, 4),
        "suggested_trailing_stop": round(suggested_stop, 2),
        "suggested_target": round(suggested_target, 2),
    }

    ai_text = ai_summary if ai_summary else f"Automated research evaluates {pos.symbol} at ${current_price:.2f} with a {action_verdict} rating based on {len(pos_factors)} bullish vs {len(neg_factors)} risk factors."

    return PositionResearchReport(
        symbol=pos.symbol,
        position_type=pos.position_type,
        current_price=round(current_price, 2),
        entry_price=round(entry_price, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        unrealized_pnl_pct=round(unrealized_pnl_pct, 4),
        action_verdict=action_verdict,
        confidence_score=round(confidence_score, 2),
        verdict_summary=verdict_summary,
        positive_factors=pos_factors,
        negative_factors=neg_factors,
        adjusted_stop_loss=round(suggested_stop, 2),
        adjusted_target_price=round(suggested_target, 2),
        technical_metrics=tech_metrics,
        risk_metrics=risk_metrics,
        ai_evidence_summary=ai_text,
    )
