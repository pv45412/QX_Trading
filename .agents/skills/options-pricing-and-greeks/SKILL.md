---
name: options-pricing-and-greeks
description: Options pricing models, Black-Scholes Greeks, 100x contract multiplier math, dynamic position sizers, and option proposal construction.
---

# Options Pricing & Greeks Engineering Protocol

This skill provides operational rules for option trade proposals, volatility calculations, and portfolio Greek risk math on the QX Platform.

## 1. Contract Multiplier Standard
- **Market Value**: `quantity * price * 100.0`
- **Portfolio Net Greeks**: `quantity * delta * 100.0`, `quantity * gamma * 100.0`, `quantity * theta * 100.0`, `quantity * vega * 100.0`

## 2. Dynamic Position Sizing Rules
- **Long Option Sizing**: `max_risk = premium * 100.0`. Sizing calculates `recommended_units = floor(max_account_risk / max_risk)`.
- **Vertical Spread Sizing**: `max_risk = analytical_max_loss`. Sizing calculates `recommended_units = floor(max_account_risk / max_risk)`.
- **Fail-Closed Rule**: If stop loss, strike width, or max loss is invalid/undefined, return `recommended_units = 0` and mark `is_valid: False`.

## 3. Trade Proposal Construction
- Option trade proposals must use the option contract symbol (e.g. `NVDA_270917C120`), mid-price, strike, expiration, and DTE.
- Never substitute the underlying stock symbol and stock limit price for option orders.
