"""
QX Options Engine: Gamma Exposure (GEX) and Dealer Positioning.
Provides 0DTE / short-dated SPX & ETF options flow, Gamma Flip calculations,
and Dealer Positioning metrics tailored for Day Traders.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class GammaExposureSnapshot:
    symbol: str
    current_price: float
    net_gamma: float
    gamma_flip_price: float
    regime: str  # 'Long Gamma (Volatility Suppressed)' vs 'Short Gamma (Volatility Accelerated)'
    expected_move_1sigma: float
    expected_move_2sigma: float
    top_call_gamma_strike: float
    top_put_gamma_strike: float
    zero_dte_volume_ratio: float
    call_put_gamma_ratio: float


def calculate_gamma_exposure(
    symbol: str,
    current_price: float,
    option_chain: pd.DataFrame,
    volatility_annual: float = 0.16,
    settlement_type: str | None = None,
) -> GammaExposureSnapshot:
    """
    Calculate Net Gamma Exposure (GEX) and Dealer Positioning across option strikes.
    option_chain expected columns: ['strike', 'option_type', 'open_interest', 'volume', 'gamma', 'dte']
    Supports settlement_type filtering ('AM' for AM-settled monthly SPX vs 'PM' for PM-settled weekly/0DTE SPXW).
    """
    if option_chain.empty or current_price <= 0:
        return _empty_gex_snapshot(symbol, current_price)

    df = option_chain.copy()

    # AM vs PM settlement segregation if specified or detected
    if settlement_type is not None:
        st_upper = settlement_type.strip().upper()
        # Helper mask checking settlement_type / settlementType column
        st_col = next((c for c in ("settlement_type", "settlementType") if c in df.columns), None)
        sym_col = next((c for c in ("symbol", "root_symbol") if c in df.columns), None)
        
        if st_upper == "PM":
            mask_st = (df[st_col].astype(str).str.upper() == "PM") if st_col else pd.Series(False, index=df.index)
            mask_sym = (df[sym_col].astype(str).str.contains("SPXW|WEEKL|0DTE", case=False, na=False)) if sym_col else pd.Series(False, index=df.index)
            mask_pm = mask_st | mask_sym
            if not mask_pm.any() and "is_pm_settled" in df.columns:
                mask_pm = df["is_pm_settled"] == True
            df = df[mask_pm] if mask_pm.any() else df[df[st_col].astype(str).str.upper() == "PM"] if st_col else df
        elif st_upper == "AM":
            mask_st_am = (df[st_col].astype(str).str.upper() == "AM") if st_col else pd.Series(True, index=df.index)
            mask_sym_am = (~df[sym_col].astype(str).str.contains("SPXW|WEEKL|0DTE", case=False, na=False)) if sym_col else pd.Series(True, index=df.index)
            df = df[mask_st_am & mask_sym_am]

    if df.empty:
        return _empty_gex_snapshot(f"{symbol}_{settlement_type}" if settlement_type else symbol, current_price)

    # If gamma is not present in feed, estimate Black-Scholes gamma proxy
    if "gamma" not in df.columns or df["gamma"].isna().all():
        df["gamma"] = _estimate_option_gamma(df, current_price, volatility_annual)

    # Dealer positioning: Dealers are short calls (negative dealer gamma contribution) and long puts (positive dealer gamma contribution)
    # GEX per strike = Open Interest * Spot * Gamma * 100 * (1 if call else -1)
    multiplier = np.where(df["option_type"].str.lower() == "call", 1.0, -1.0)
    df["gex"] = df["open_interest"] * df["gamma"] * (current_price ** 2) * 0.01 * multiplier

    net_gamma = float(df["gex"].sum())

    # Call / Put strikes breakdown
    call_df = df[df["option_type"].str.lower() == "call"]
    put_df = df[df["option_type"].str.lower() == "put"]

    top_call_strike = float(call_df.groupby("strike")["gex"].sum().idxmax()) if not call_df.empty else current_price
    top_put_strike = float(put_df.groupby("strike")["gex"].sum().abs().idxmax()) if not put_df.empty else current_price

    call_gex_total = float(call_df["gex"].sum()) if not call_df.empty else 0.0
    put_gex_abs = float(put_df["gex"].abs().sum()) if not put_df.empty else 1.0
    cp_ratio = call_gex_total / put_gex_abs if put_gex_abs > 0 else 1.0

    # Gamma Flip estimation: Find strike where cumulative gamma crosses zero
    strikes = np.sort(df["strike"].unique())
    gex_by_strike = df.groupby("strike")["gex"].sum().reindex(strikes, fill_value=0.0)
    cum_gex = gex_by_strike.cumsum()
    
    # Locate zero crossing nearest spot price
    flip_idx = (np.abs(cum_gex.values)).argmin()
    gamma_flip_price = float(strikes[flip_idx]) if len(strikes) > 0 else current_price

    # 1-Sigma & 2-Sigma expected 1-day move calculation
    daily_vol = (volatility_annual / np.sqrt(252))
    expected_1sig = current_price * daily_vol
    expected_2sig = expected_1sig * 2.0

    # Determine market volatility regime
    regime = "Long Gamma (Volatility Suppressed)" if net_gamma >= 0 else "Short Gamma (Volatility Accelerated)"

    # 0DTE Volume ratio
    zero_dte_vol = float(df.loc[df["dte"] == 0, "volume"].sum()) if "dte" in df.columns else 0.0
    total_vol = float(df["volume"].sum()) if "volume" in df.columns else 1.0
    zero_dte_ratio = zero_dte_vol / total_vol if total_vol > 0 else 0.0

    return GammaExposureSnapshot(
        symbol=symbol.upper(),
        current_price=round(current_price, 2),
        net_gamma=round(net_gamma, 2),
        gamma_flip_price=round(gamma_flip_price, 2),
        regime=regime,
        expected_move_1sigma=round(expected_1sig, 2),
        expected_move_2sigma=round(expected_2sig, 2),
        top_call_gamma_strike=round(top_call_strike, 2),
        top_put_gamma_strike=round(top_put_strike, 2),
        zero_dte_volume_ratio=round(zero_dte_ratio, 4),
        call_put_gamma_ratio=round(cp_ratio, 2),
    )


def _estimate_option_gamma(df: pd.DataFrame, spot: float, vol: float, r: float = 0.045) -> pd.Series:
    """Estimates exact Black-Scholes option gamma incorporating risk-free rate r."""
    dte = df["dte"].clip(lower=1) / 365.0 if "dte" in df.columns else pd.Series(1 / 365.0, index=df.index)
    moneyness = np.log(spot / df["strike"])
    d1 = (moneyness + (r + 0.5 * (vol ** 2)) * dte) / (vol * np.sqrt(dte))
    n_prime = (1.0 / np.sqrt(2 * np.pi)) * np.exp(-0.5 * (d1 ** 2))
    gamma = n_prime / (spot * vol * np.sqrt(dte))
    return gamma.fillna(0.0)


def _empty_gex_snapshot(symbol: str, price: float) -> GammaExposureSnapshot:
    return GammaExposureSnapshot(
        symbol=symbol.upper(),
        current_price=price,
        net_gamma=0.0,
        gamma_flip_price=price,
        regime="Neutral",
        expected_move_1sigma=round(price * 0.01, 2),
        expected_move_2sigma=round(price * 0.02, 2),
        top_call_gamma_strike=price,
        top_put_gamma_strike=price,
        zero_dte_volume_ratio=0.0,
        call_put_gamma_ratio=1.0,
    )


def calculate_segregated_gamma_exposure(
    symbol: str,
    current_price: float,
    option_chain: pd.DataFrame,
    volatility_annual: float = 0.16,
) -> dict[str, GammaExposureSnapshot]:
    """
    Calculate segregated Net Gamma Exposure (GEX) separating PM-settled weekly/0DTE (SPXW)
    from AM-settled monthly (SPX) gamma walls to prevent false pinning levels.
    """
    return {
        "PM_WEEKLY": calculate_gamma_exposure(symbol, current_price, option_chain, volatility_annual, settlement_type="PM"),
        "AM_MONTHLY": calculate_gamma_exposure(symbol, current_price, option_chain, volatility_annual, settlement_type="AM"),
        "COMBINED": calculate_gamma_exposure(symbol, current_price, option_chain, volatility_annual, settlement_type=None),
    }

