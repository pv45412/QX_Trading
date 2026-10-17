# Low-Fidelity Product Wireframes

These wireframes define hierarchy only. They are not production JSX, visual styling,
or approval of new backend behavior.

## Today

```text
+----------------------------------------------------------------------------------+
| QX | Today | Opportunities | Trade | Portfolio | Research | System               |
| Horizon: [DAY] [SWING] [INVEST]              Data as of ...   Health: OK/PARTIAL |
+----------------------------------------------------------------------------------+
| WHAT MATTERS NOW?                                                               |
| Session | Market pulse | Regime | Volatility | Material freshness warning       |
+-----------------------------------------------+----------------------------------+
| MARKET DRIVERS                                | POSITIONS REQUIRING ATTENTION    |
| Primary: <backend supplied / unavailable>      | 1. Symbol - reason - risk state  |
| Strength / persistence / coverage              | 2. Symbol - reason - stale data  |
| Confirming ... | Conflicting ...               | [Open Portfolio]                 |
+-----------------------------------------------+----------------------------------+
| ACTIVE QX OPPORTUNITIES                                                          |
| Symbol | State | Direction | Trigger | Invalidation | Risk | Freshness | [Open]  |
| ...                                                                              |
| [View all Opportunities]                                                         |
+----------------------------------------------------------------------------------+
| IMPORTANT EVENTS / DATA HEALTH (only material exceptions)                       |
| Provider issue or supported event | impact | [Open System/Research]             |
+----------------------------------------------------------------------------------+
```

Mobile order: identity/health warning -> market pulse -> active opportunities ->
positions requiring attention -> market driver -> material events.

## Opportunities

```text
+----------------------------------------------------------------------------------+
| QX | Today | Opportunities | Trade | Portfolio | Research | System               |
+----------------------------------------------------------------------------------+
| OPPORTUNITIES   Horizon [DAY] [SWING] [INVEST]   View [List] [Cards] [Heatmap]   |
| Filters: State | Direction | Playbook/Thesis | Sector | Freshness | Coverage     |
+----------------------------------------------------------------------------------+
| SYMBOL | LIFECYCLE | DIR | PLAYBOOK/THESIS | DRIVER | TRIGGER / INVALIDATION     |
|        | TRADEABILITY | OPTIONS | PORTFOLIO | COVERAGE | DATA AS OF              |
|----------------------------------------------------------------------------------|
| SPY    | ARMED     | ... | ...  | ... | 000 / 000 | pending | -- | -- | 86% ... |
| NVDA   | BLOCKED   | ... | ...  | ... | --        | --      | -- | -- | 42% ... |
|----------------------------------------------------------------------------------|
| Selecting a row opens Trade Workspace using its canonical evaluation identity.   |
+----------------------------------------------------------------------------------+
| Empty state: No opportunities meet current canonical filters. No fallback rows.  |
+----------------------------------------------------------------------------------+
```

Mobile cards lead with symbol, state, trigger/invalidation, risk status, and freshness;
secondary evidence is collapsed.

## Trade Workspace

```text
+----------------------------------------------------------------------------------+
| QX | Today | Opportunities | Trade | Portfolio | Research | System               |
| Symbol [SPY] Horizon [DAY] Timeframe [5m] Evaluate [read-only] Data as of ...     |
+----------------------------------------------------------------------------------+
| DECISION SUMMARY                                                                 |
| STATE: ARMED        Direction: Bearish        Playbook: <canonical>               |
| What is happening? <driver/regime summary>                                       |
| Waiting for: <trigger condition>          Wrong at: <invalidation>                |
| Is there a trade? Not yet - trigger pending                                      |
+----------------------------------------------------------------------------------+
| MARKET DRIVER (backend supplied or unavailable)                                  |
| Primary | Strength | Persistence | Confirming | Conflicting | Coverage            |
+----------------------------------------------------------------------------------+
| LIFECYCLE                                                                        |
| [WATCH] -> [ARMED] -> [TRIGGERED] -> [TRADEABLE] -> [OPTIONS] -> [PORTFOLIO]     |
| Terminal branch: BLOCKED / NO_SETUP / NOT_TRADEABLE / ... when applicable       |
+------------------------------------------+---------------------------------------+
| STRUCTURE / REGIME / DIRECTION           | TRIGGER / INVALIDATION / TARGETS      |
| Readable summaries + coverage            | Planned/confirmed + event timestamp   |
+------------------------------------------+---------------------------------------+
| PARTICIPATION / TRADEABILITY             | OPTIONS EXPRESSION                    |
| State | coverage | structural R:R         | Suitability | strategy | max loss     |
+------------------------------------------+---------------------------------------+
| PORTFOLIO RISK                           | FUTURE EXECUTION READINESS            |
| Decision | binding constraint | cap       | Disabled: Phase 11 not enabled        |
+----------------------------------------------------------------------------------+
| > WHY / EVIDENCE / PROVENANCE / STAGE LATENCY / RAW AUDIT                       |
+----------------------------------------------------------------------------------+
```

Mobile order: symbol/state -> five-question summary -> lifecycle -> trigger/invalidation
-> tradeability -> options -> portfolio -> structure/context -> WHY.

## Portfolio

```text
+----------------------------------------------------------------------------------+
| QX | Today | Opportunities | Trade | Portfolio | Research | System               |
| Account [internal label]  Snapshot ...  Freshness ...  Provider ...              |
+----------------------------------------------------------------------------------+
| BROKER PORTFOLIO SUMMARY                                                         |
| Equity | Cash/Buying power if required | Open risk | Net/Gross exposure          |
+------------------------------------------+---------------------------------------+
| EXPOSURE / CONCENTRATION                 | CONSTRAINTS                            |
| Sector | Single name | Asset class       | Binding limit | headroom | provenance  |
| PARTIAL if sector provenance incomplete  | Last Phase 10 decision                |
+------------------------------------------+---------------------------------------+
| POSITIONS REQUIRING ATTENTION                                                    |
| Symbol | reason | lifecycle link | risk | freshness | [Open Position]           |
+----------------------------------------------------------------------------------+
| ALL POSITIONS                                                                    |
| Symbol | Qty | Value | P/L | Sector/status | Greeks | Open risk | [Trade] [Research]|
+----------------------------------------------------------------------------------+
| > ACCOUNT/RISK EVIDENCE AND PROVENANCE                                           |
+----------------------------------------------------------------------------------+
| Note: ETF constituent research is located under Research, not Portfolio.          |
+----------------------------------------------------------------------------------+
```

## Research

```text
+----------------------------------------------------------------------------------+
| QX | Today | Opportunities | Trade | Portfolio | Research | System               |
| [Instrument] [ETF & Sector] [Options & Strategy] [Historical] [Backtests]         |
+----------------------------------------------------------------------------------+
| Subject [MSFT]  Period [...]  As of [...]  Provenance [...]  [Open in Trade]      |
+----------------------------------------------------------------------------------+
| RESEARCH SUMMARY                                                                 |
| Thesis/context | supported source labels | limitations                            |
+------------------------------------------+---------------------------------------+
| STRUCTURE / RELATIVE STRENGTH             | SECTOR / BENCHMARK CONTEXT            |
| chart, historical events, timeframe       | ranking, rotation, comparison         |
+------------------------------------------+---------------------------------------+
| MODE-SPECIFIC WORKSPACE                                                           |
| Instrument: history and structure                                                 |
| ETF & Sector: constituents and fund concentration                                 |
| Options & Strategy: modeled ideas and payoff                                      |
| Backtests: approved replay results; no automatic optimization                     |
+----------------------------------------------------------------------------------+
| > DATA PROVENANCE / MODEL ASSUMPTIONS / LIMITATIONS                              |
+----------------------------------------------------------------------------------+
```

Research may be dense, but each mode has one primary object and clearly labels
canonical, source-backed, modeled, static, user-entered, and legacy outputs.
