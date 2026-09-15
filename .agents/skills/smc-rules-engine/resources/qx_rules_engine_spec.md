# QX System: Institutional Rules Engine & Signal Generation Specification

## 1. Executive Summary & Architectural Vision

The **QX System Rules Engine** is an institutional-grade, multi-factor decision engine designed for intraday equity, index, options, and futures trading. It synthesizes insights from **Smart Money Concepts (SMC)**, **Auction Market Theory (Market Profile)**, **Cumulative Volume Delta (CVD)**, **James Boyd Market Phases**, and **Options Dealer Gamma Exposure (GEX)**.

By unifying your complete suite of 12 ThinkScript institutional modules with top-tier quantitative TradingView research (LuxAlgo SMC, Volume Profile, CVD Divergence), QX replaces subjective trading with **probabilistic, rule-governed execution**.

---

## 2. Master Institutional Indicator Catalog (12 TOS Modules)

| # | Study Name | File Reference | Quantitative Purpose & Logic |
| :---: | :--- | :--- | :--- |
| **1** | **Cumulative Delta Volume (CVD Scaled)** | [`tos_cumulative_delta_volume.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_cumulative_delta_volume.tos) | Scaled Net Delta ($Volume \times (Rate_{up} - Rate_{dn}) \times 0.10$) with Globex 17:00 reset & 1.618 StDev bands. |
| **2** | **QX Magicline Radar v1.8** | [`tos_magicline_radar.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_magicline_radar.tos) | D1/D2/D3 High/Low/Mid level radar with ATR proximity classification ($0.15\sigma$ Test, $0.40\sigma$ Near). |
| **3** | **James Boyd 5 Market Phases** | [`tos_james_boyd_market_phases.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_james_boyd_market_phases.tos) | 5-Phase trend lifecycle (P1: Downtrend, P2: Early Reversal, P3: Strong Uptrend, P4: Pullback Warning via HullMA, P5: Support Bounce). |
| **4** | **RS Percentile Rank vs SPX** | [`tos_rs_percentile_rank.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_rs_percentile_rank.tos) | Relative Strength Percentile ranking against SPX over 10-day/252-day rolling window (Tiers $>80, 60-80, 40-60, 20-40, \le 20$). |
| **5** | **Bull & Bear Flag Engine** | [`tos_bull_bear_flag_engine.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_bull_bear_flag_engine.tos) | Flag pattern recognition with MACD Histogram pullback ($Hist[1] < Hist[2]$) & 10/50 EMA reversal triggers. |
| **6** | **Breakout / Breakdown Tracker** | [`tos_breakout_breakdown_tracker.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_breakout_breakdown_tracker.tos) | 15-period Highest High / Lowest Low breakout & re-test tracking ("TODAY BO", "TESTING YESTERDAY BO"). |
| **7** | **SMC Complete Suite v3.1** | [`tos_smc_complete_suite.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_smc_complete_suite.tos) | Multi-Timeframe BOS/CHoCH, Fair Value Gaps, Order Blocks, Liquidity Pools (EQH/EQL). |
| **8** | **Delta Absorption Engine v2.1** | [`tos_delta_absorption_engine.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_delta_absorption_engine.tos) | Limit Order Absorption (Trapped Buyers/Sellers via wick-to-body ratio $\ge 1.5\text{x}$) & Volume Exhaustion Climaxes. |
| **9** | **Anchored VScore v3.1** | [`tos_anchored_vscore.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_anchored_vscore.tos) | Volume-Weighted Standard Score ($(P - \text{AVWAP}) / \sigma$) with auto-anchors (Globex 18:00, RTH 09:30, Week, Month, YTD). |
| **10** | **Clean Execution Suite v15.3** | [`tos_clean_execution.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_clean_execution.tos) | Multi-Market Confluence Execution for `/NQ`, `/ES`, `/CL` with tick-scaled risk limits & 4-bar target shelves. |
| **11** | **VScore Pressure Oscillator v1.5** | [`tos_vscore_pressure_oscillator.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_vscore_pressure_oscillator.tos) | Participation RVOL classification (Low, Normal, Confirmed $\ge 1.30\text{x}$) + VScore Buying/Selling Easing Momentum. |
| **12** | **Session Auction Engine v2.0** | [`tos_session_auction_engine.tos`](file:///c:/Project/2026/.agents/skills/smc-rules-engine/resources/tos_session_auction_engine.tos) | Developing AVWAP, Value Area Bands ($\pm 1\sigma, \pm 2\sigma$), 30-min Initial Balance (IB High/Low), and Prior Day High/Low. |

---

## 3. Signal Scoring Matrix & Confluence Formula

$$\text{QX Score} = 0.25 S_{\text{SMC}} + 0.20 S_{\text{Phases}} + 0.20 S_{\text{CVD\_Absorption}} + 0.15 S_{\text{VScore}} + 0.10 S_{\text{RS\_Rank}} + 0.10 S_{\text{OptionsFlow}}$$

#### Decision Thresholds:
* **QX Score $\ge 70/100$**: Trigger **BUY CALL / LONG** Limit Order.
* **QX Score $\le 30/100$**: Trigger **BUY PUT / SHORT** Limit Order.
* **$30 < \text{QX Score} < 70$**: **WAIT** (Neutral / Consolidation).
