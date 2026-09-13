# QX Platform — Future-Ready Architecture for AI Agent

**Status:** Architecture source of truth for the QX platform rebuild  
**Purpose:** Guide the AI coding agent while the current pages are being redesigned so the platform is ready for future integrations without requiring another major rewrite.  
**Primary principle:** Pages are consumers of domain services. Pages must never become the architecture.

---

## 1. Executive Architecture Decision

The current consolidation is a good starting point, but this rebuild should establish the long-term QX platform structure.

The target is a **modular monolith** with:

- one React web application,
- one FastAPI backend,
- reusable QX domain engines,
- shared financial calculations,
- market-data provider abstraction,
- broker provider abstraction,
- strategy modules,
- position-management services,
- live scanner services,
- AI explanation services,
- alerts and notifications,
- lightweight telemetry,
- future integration readiness.

The platform is a **live-decision and position-management system**.

### Explicitly out of scope

Do **not** build:

- paper trading,
- historical backtesting,
- tick replay,
- historical option-chain warehousing,
- simulation engines,
- large-scale historical market-data storage,
- machine-learning optimization,
- automated live order execution at this stage.

These add major data, infrastructure, and maintenance complexity and are not required for the current goal.

---

# 2. Current-State Facts

The consolidated workspace is:

```text
C:\Project\2026\
```

Current platform direction:

```text
React UI      :5174
FastAPI API   :8510
```

The system has already moved toward:

- one master React dashboard,
- one FastAPI backend,
- one shared Python environment,
- one central cache hierarchy,
- consolidated configuration,
- consolidated tests.

Existing or partially implemented functional areas include:

- Research
- Position Advisor
- Options Scanner
- SPX Calendars
- Futures Workspace
- AI Evidence Review
- Shared indicators
- Shared market-data cache

---

# 3. Core Architecture Principles

## 3.1 Domain Logic Must Not Live in React

React may:

- collect user input,
- display results,
- control view state,
- call APIs.

React must not calculate:

- RSI,
- ATR,
- IV Rank,
- expected move,
- structure scores,
- strategy selection,
- option construction,
- position-health decisions,
- risk sizing.

Correct:

```text
React
  ↓
FastAPI
  ↓
Application Service
  ↓
Domain Engine
  ↓
Provider / Repository
```

---

## 3.2 One Calculation, One Source of Truth

Never duplicate financial calculations.

Canonical shared implementations must exist for:

- RSI
- ATR
- EMA
- SMA
- VWAP
- RVOL
- Relative Strength
- Historical Volatility
- Forecast Volatility
- IV Rank
- IV Percentile
- Expected Move
- Skew
- Term Structure
- BOS
- CHoCH
- FVG
- Option Greeks normalization
- Risk/Reward
- Position Sizing
- Spread Payoff
- Liquidity checks

Incorrect:

```text
scanner/rsi.py
advisor/rsi.py
research/rsi.py
```

Correct:

```text
qx/indicators/momentum/rsi.py
```

---

## 3.3 Pages Are Workspaces, Not Backend Domains

UI pages may include:

```text
Dashboard
Scanner
Research
Positions
Strategies
Futures
Portfolio
Alerts
Settings
```

But the backend should be organized around reusable capabilities, not page names.

---

# 4. Target Platform Architecture

```text
                         QX PLATFORM
                              │
            ┌─────────────────┴─────────────────┐
            │                                   │
       React Web App                        FastAPI API
                                                │
                                    ┌───────────┴───────────┐
                                    │                       │
                              Application Layer        Event / Jobs
                                    │
                            ┌───────┴────────┐
                            │                │
                         QX Core         Orchestration
                            │
      ┌─────────────────────┼─────────────────────────┐
      │                     │                         │
 Market Intelligence   Opportunity Engine     Position Engine
      │                     │                         │
      └─────────────────────┼─────────────────────────┘
                            │
                      Strategy Modules
                            │
                      Trade Construction
                            │
                         Risk Engine
                            │
                     Provider Abstraction
                            │
             ┌──────────────┼──────────────┐
             │              │              │
        Market Data       Broker          AI
             │              │              │
             └──────────────┴──────────────┘
                            │
                    Lightweight Telemetry
```

---

# 5. Recommended Repository Structure

```text
C:\Project\2026\
│
├── apps/
│   ├── api/
│   │   ├── routes/
│   │   ├── schemas/
│   │   ├── dependencies/
│   │   └── main.py
│   │
│   └── web/
│       └── src/
│           ├── app/
│           ├── pages/
│           ├── features/
│           ├── components/
│           ├── hooks/
│           ├── services/
│           └── state/
│
├── qx/
│   ├── core/
│   │   ├── models/
│   │   ├── enums/
│   │   ├── errors/
│   │   └── time/
│   │
│   ├── indicators/
│   │   ├── momentum/
│   │   ├── trend/
│   │   ├── volatility/
│   │   ├── volume/
│   │   └── structure/
│   │
│   ├── market/
│   │   ├── regime/
│   │   ├── breadth/
│   │   ├── relative_strength/
│   │   └── sessions/
│   │
│   ├── options/
│   │   ├── chain/
│   │   ├── greeks/
│   │   ├── volatility/
│   │   ├── liquidity/
│   │   ├── expected_move/
│   │   ├── assignment/
│   │   └── expiration/
│   │
│   ├── structure/
│   │   ├── bos/
│   │   ├── choch/
│   │   ├── fvg/
│   │   ├── swings/
│   │   └── vwap/
│   │
│   ├── scanner/
│   │   ├── universe/
│   │   ├── scoring/
│   │   ├── ranking/
│   │   └── opportunity/
│   │
│   ├── strategies/
│   │   ├── selector/
│   │   ├── debit_spreads/
│   │   ├── credit_spreads/
│   │   ├── calendars/
│   │   ├── diagonals/
│   │   ├── leaps/
│   │   ├── pmcc/
│   │   ├── wheel/
│   │   └── iron_condor/
│   │
│   ├── construction/
│   │   ├── dte/
│   │   ├── strikes/
│   │   ├── width/
│   │   ├── entry/
│   │   ├── targets/
│   │   └── invalidation/
│   │
│   ├── positions/
│   │   ├── health/
│   │   ├── advisor/
│   │   ├── lifecycle/
│   │   ├── adjustment/
│   │   └── roll/
│   │
│   ├── risk/
│   │   ├── position_size/
│   │   ├── exposure/
│   │   └── limits/
│   │
│   ├── portfolio/
│   │   ├── holdings/
│   │   ├── pnl/
│   │   ├── greeks/
│   │   └── allocation/
│   │
│   ├── telemetry/
│   │   ├── signals/
│   │   ├── decisions/
│   │   └── outcomes/
│   │
│   ├── alerts/
│   └── ai/
│
├── integrations/
│   ├── market_data/
│   │   ├── base.py
│   │   ├── schwab/
│   │   ├── polygon/
│   │   ├── tradier/
│   │   └── yfinance/
│   │
│   ├── brokers/
│   │   ├── base.py
│   │   └── schwab/
│   │
│   ├── llm/
│   │   ├── base.py
│   │   └── openai/
│   │
│   └── notifications/
│
├── persistence/
│   ├── repositories/
│   ├── models/
│   └── migrations/
│
├── workers/
│   ├── scanner_jobs/
│   ├── market_refresh/
│   └── alerts/
│
├── config/
│   ├── scoring/
│   ├── strategies/
│   ├── risk/
│   └── providers/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── regression/
│
├── data/
│   └── cache/
│
├── pyproject.toml
├── .env.example
└── README.md
```

---

# 6. Domain Boundaries

## 6.1 Market Intelligence

Answers:

> What is happening in the market and this underlying?

Responsible for:

- market regime,
- VIX state,
- breadth,
- relative strength,
- structure,
- momentum,
- volatility,
- volume participation.

It does not recommend a trade.

---

## 6.2 Opportunity / Scanner Engine

Answers:

> What should I consider trading?

Pipeline:

```text
Universe
   ↓
Data / Liquidity Veto
   ↓
Direction Engine ───────┐
                        ├── QX Opportunity Score
Volatility Engine ──────┘
                        ↓
Strategy Selector
                        ↓
Trade Construction
                        ↓
Risk Check
                        ↓
Ranked Opportunity
```

---

## 6.3 Position Management Engine

Answers:

> I already own this position. What should I do now?

Possible outputs:

```text
STRONG HOLD
HOLD
HOLD / TIGHTEN
TRIM
EXIT
ROLL
ADJUST
REVIEW
```

This must remain separate from Scanner logic.

Scanner decides whether to enter.

Position Management decides what to do after entry.

---

# 7. Position Advisor Redesign

The current rule-based advisor is a useful MVP, but hard rules such as:

```text
P&L >= 25% AND RSI > 68 → TRIM
```

should not remain the primary architecture.

Use a Position Health Score.

Initial configurable model:

```text
Trend Health               20%
Structure Quality          20%
Momentum                   10%
Volatility State           10%
Distance from Invalidation 15%
Remaining Reward           15%
Risk Deterioration         10%
```

Initial interpretation:

```text
85–100  STRONG HOLD
70–84   HOLD
55–69   HOLD / TIGHTEN
40–54   TRIM / ADJUST
<40     EXIT / REVIEW
```

Hard overrides are still allowed for true risk events.

Examples:

```text
Stop invalidated
→ EXIT / REVIEW

Assignment risk materially elevated
→ ADJUST / REVIEW

Expiration operational risk
→ ROLL / CLOSE
```

---

# 8. Options Scanner Architecture

## 8.1 Pipeline

```text
0. DATA QUALITY / LIQUIDITY VETO
          ↓
1. MARKET REGIME
          ↓
      ┌───────────────┐
      │               │
2A. DIRECTION     2B. VOLATILITY
    ENGINE            ENGINE
      │               │
      └───────┬───────┘
              ↓
3. QX OPPORTUNITY SCORE
              ↓
4. STRATEGY SELECTOR
              ↓
5. TRADE CONSTRUCTION
              ↓
6. RISK CHECK
              ↓
7. SCANNER RESULT
              ↓
8. LIGHT TELEMETRY
```

## 8.2 True Hard Vetoes

Use binary gates only for real disqualifiers:

- stale quote,
- corrupt data,
- incomplete required option chain,
- option liquidity below configured minimum,
- bid/ask spread above configured maximum,
- selected strike untradeable,
- explicit normal-mode event blackout,
- configured risk violation.

Do not convert ordinary technical factors into hard gates.

---

# 9. Direction Engine

The Direction Engine answers:

> What is the directional state and how strong is it?

Inputs may include:

- BOS
- CHoCH
- FVG
- VWAP
- EMA stack
- Relative Strength
- RVOL
- cumulative delta / volume pressure
- trend slope
- momentum

Initial weights should be configuration-driven.

Example:

```yaml
direction_score:
  bos_choch: 0.20
  fvg: 0.10
  vwap: 0.15
  trend_alignment: 0.15
  relative_strength: 0.15
  rvol: 0.10
  delta_pressure: 0.15
```

These are starting defaults, not proven edge.

---

# 10. Volatility Engine

The Volatility Engine answers:

> Is volatility cheap, fair, or expensive relative to expected future movement?

Inputs:

- IV
- IV Rank
- IV Percentile
- historical volatility,
- forecast realized volatility,
- IV / forecast-RV,
- skew,
- term structure,
- expected move,
- event state.

For V1 use an EWMA-based realized-volatility forecast.

Do not depend only on trailing HV20.

---

# 11. Strategy Engine

The Strategy Engine consumes:

- directional state,
- structure strength,
- volatility state,
- expected move,
- market regime,
- liquidity,
- scan mode,
- DTE mode.

Avoid one massive nested `if/elif` block.

Use strategy compatibility scoring.

Concept:

```text
Candidate Strategies
        ↓
Compatibility Score
        ↓
Liquidity Feasibility
        ↓
Risk Feasibility
        ↓
Ranked Strategy Recommendations
```

Return:

- one primary strategy,
- optional alternatives,
- reasons.

---

# 12. Strategy Modules

Each strategy owns strategy-specific rules.

Examples:

```text
Bull Call Debit Spread
Bear Put Debit Spread
Bull Put Credit Spread
Bear Call Credit Spread
Long Call
Long Put
Calendar
Diagonal
Iron Condor
LEAP
PMCC
Wheel
```

Each module should expose behavior similar to:

```python
evaluate_compatibility(context)
construct_trade(context)
validate_liquidity(trade)
calculate_risk(trade)
management_plan(trade)
```

Do not bury these rules inside Scanner code.

---

# 13. SPX Calendar Engine

SPX Calendars remain a specialized strategy module.

They can reuse shared:

- option chains,
- IV,
- term structure,
- Greeks,
- liquidity,
- event state,
- risk.

Calendar-specific logic remains isolated:

- front/back expiration selection,
- IV term-structure edge,
- delta-neutrality rules,
- debit limits,
- event timing,
- calendar-specific adjustment logic.

---

# 14. Trade Construction Engine

Strategy selection and construction are different concerns.

Example:

```text
Strategy Selector:
Bull Call Spread

Trade Construction:
Choose expiration
Choose long strike
Choose short strike
Choose width
Calculate debit
Calculate max risk
Calculate max profit
Calculate break-even
```

Outputs:

- expiration,
- DTE,
- strikes,
- deltas,
- width,
- debit or credit,
- max risk,
- max profit where defined,
- break-even,
- entry,
- invalidation,
- targets,
- liquidity quality,
- reward/risk.

Liquidity must be rechecked on the actual selected strikes.

---

# 15. Risk Engine

Shared responsibilities:

- allowed risk per trade,
- strategy max-loss validation,
- portfolio exposure validation,
- position-size calculation,
- max concurrent risk,
- future sector/correlation rules if needed.

Initial sizing model:

```text
A+    0.75–1.00%
A     0.50–0.75%
B     0.25–0.50%
Below B → no trade
```

Formula:

```text
Allowed Dollar Risk
÷
Maximum Strategy Loss
=
Position Size
```

---

# 16. Market-Data Provider Abstraction

Do not couple QX to a single vendor.

Interface example:

```python
class MarketDataProvider:
    def get_quote(...)
    def get_bars(...)
    def get_option_chain(...)
    def get_greeks(...)
    def get_market_calendar(...)
```

Possible implementations:

```text
SchwabProvider
PolygonProvider
TradierProvider
YFinanceProvider
MockProvider
```

Domain engines must not know which vendor supplies the data.

Correct:

```text
Scanner
  ↓
MarketDataService
  ↓
MarketDataProvider
```

---

# 17. Broker Abstraction

Even without live automated execution, define the boundary now.

```python
class BrokerProvider:
    def get_accounts(...)
    def get_positions(...)
    def get_orders(...)
    def preview_order(...)
    def place_order(...)
    def cancel_order(...)
```

Live order placement remains disabled unless explicitly enabled later.

The purpose is future readiness, not current automation.

---

# 18. Data Freshness

Every external market value should internally carry:

- source,
- as-of timestamp,
- market session,
- timeframe,
- freshness state.

Example:

```json
{
  "value": 158.47,
  "source": "schwab",
  "as_of": "2026-09-13T14:31:02-04:00",
  "freshness": "live"
}
```

Never represent stale data as live.

---

# 19. Global Instrument Context

The UI should support shared context for:

```text
Symbol
Asset Type
Timeframe
Portfolio / Account
Mode
```

Selecting a symbol in Scanner should make it easy to inspect the same symbol in Research or Positions.

Do not duplicate symbol state unnecessarily per page.

---

# 20. UI Workspaces

Recommended top-level workspaces:

```text
Dashboard
Scanner
Research
Positions
Strategies
Futures
Portfolio
Alerts
Settings
```

Not all need to be completed in V1.

## Scanner

Primary purpose:

> Rank live opportunities.

Suggested table:

```text
Ticker
QX Score
Bias
Structure
Volatility
Strategy
DTE
Risk/Reward
Grade
Status
```

## Research

Primary purpose:

> Explain the underlying and the setup.

## Positions

Primary purpose:

> Manage existing trades.

## Strategies

Strategy-specific workspaces such as:

- SPX Calendars
- LEAPS
- PMCC
- Wheel
- Credit Spreads

---

# 21. API Design

Prefer domain-oriented endpoints.

Examples:

```text
GET  /api/market/{symbol}/snapshot
GET  /api/market/{symbol}/structure
GET  /api/options/{symbol}/chain

POST /api/scanner/run
GET  /api/scanner/signals/{signal_id}

POST /api/strategies/recommend
POST /api/trades/construct

POST /api/positions/evaluate
POST /api/positions/{id}/roll-analysis

GET  /api/portfolio/summary
GET  /api/telemetry/signals
```

Do not create APIs named after React components.

---

# 22. Background Jobs

Allow asynchronous background work for:

- market refresh,
- scanner refresh,
- option-chain refresh,
- alert evaluation,
- telemetry updates,
- position monitoring.

The first implementation may be lightweight.

Preserve a clean boundary so job infrastructure can be upgraded later without rewriting QX domain logic.

---

# 23. Persistence Strategy

Separate short-lived and durable data.

## Short-Lived Market Cache

Store only what is needed operationally:

- quotes,
- bars,
- chains,
- Greeks,
- recent derived snapshots.

## Durable Application State

Store:

- settings,
- watchlists,
- portfolios,
- positions,
- strategy configuration,
- user preferences.

## Lightweight Telemetry

Store only enough to audit and improve live decisions:

```text
signal_id
timestamp
symbol
underlying_price

market_regime

direction_score
structure_score
volatility_score
qx_score

recommended_strategy
strategy_score

expiration
DTE
strikes
deltas

entry
invalidation
targets

max_risk
risk_reward

configuration_version
scoring_version
data_source
```

Optionally record manual/live outcome later:

```text
final_outcome
P&L
exit_reason
```

Do not build large historical replay datasets.

---

# 24. Version Decision Logic

Each signal should record:

```text
scoring_version
strategy_version
risk_version
configuration_version
```

This allows later comparison when rules change.

---

# 25. Configuration Architecture

Do not scatter thresholds throughout the codebase.

Use:

```text
Environment
   ↓
Typed Settings
   ↓
Versioned Domain Config
   ↓
Domain Engines
```

Example:

```yaml
liquidity:
  max_spread_pct: 0.08
  min_open_interest: 500

risk:
  max_risk_pct:
    A_PLUS: 0.01
    A: 0.0075
    B: 0.005
```

---

# 26. Environment Handling

Use:

```text
.env.example
.env.local
```

and typed settings:

```text
MarketDataSettings
BrokerSettings
ScannerSettings
RiskSettings
AISettings
CacheSettings
DatabaseSettings
```

Avoid random `os.getenv()` calls across domain files.

---

# 27. AI Architecture

AI is an explanation and assistance layer.

Possible uses:

- explain why a setup ranked highly,
- summarize position risk,
- compare strategies,
- explain conflicting indicators,
- generate a market game plan,
- explain scanner output,
- summarize portfolio risk.

Correct:

```text
QX Deterministic Engine
        ↓
Structured Evidence Packet
        ↓
AI Explanation
```

Incorrect:

```text
Raw prices
   ↓
LLM decides the trade
```

---

# 28. AI Availability Semantics

Do not claim AI is connected when it is unavailable.

Recommended state:

```json
{
  "service_available": true,
  "mode": "deterministic",
  "ai_requested": true,
  "ai_connected": false,
  "fallback_active": true
}
```

---

# 29. Data-Consistency Protection

Every metric should have internal metadata:

```text
metric_id
value
timeframe
lookback
source
calculation_version
as_of
```

Narratives must reference the same metric object used by the deterministic engine.

Do not calculate narrative values separately.

---

# 30. Alerts

Alerts should consume domain events.

Examples:

```text
signal.created
position.stop_near
position.invalidation
position.roll_window
position.target_reached
market.regime_changed
strategy.high_score
```

Do not put alert logic directly in React components.

---

# 31. Future Real-Time Architecture

V1 may use:

- REST,
- scheduled refresh,
- centralized cache,
- lightweight background polling.

Keep interfaces compatible with future:

- WebSocket,
- Server-Sent Events,
- streaming market data,
- pub/sub.

Do not introduce complex streaming infrastructure now.

---

# 32. Testing Architecture

Focus on financial correctness.

## Unit Tests

Test:

- RSI
- ATR
- HV
- EWMA forecast volatility
- IV Rank
- Expected Move
- Structure detection
- Spread payoff
- Risk sizing
- Score normalization

## Strategy Tests

Given a fixed market snapshot:

- strategy ranking is deterministic,
- strike selection is deterministic,
- max risk is reproducible.

## Provider Contract Tests

Every MarketDataProvider must satisfy the same interface.

## Cross-Module Invariants

Examples:

- Scanner and Research must report the same RSI for the same symbol/timeframe.
- Position Advisor and Research must report the same ATR.
- Trade Construction max loss must equal Risk Engine max loss.
- UI narrative must match numeric backend values.

---

# 33. Observability

Record:

- request id,
- job id,
- provider,
- symbol,
- elapsed time,
- cache hit/miss,
- data timestamp,
- scoring version,
- errors.

This is essential for future debugging.

---

# 34. Error Handling

Never silently substitute invalid data with zero.

Bad:

```text
IV = 0
```

because a provider failed.

Better:

```text
volatility_state = unavailable
reason = OPTION_CHAIN_PROVIDER_TIMEOUT
```

---

# 35. Page Rebuild Rules

Because the pages are being rebuilt now:

1. Do not port legacy page logic line-by-line.
2. Extract reusable business logic first.
3. Remove duplicate calculations.
4. Keep UI state separate from trading state.
5. Every page must consume typed API contracts.
6. Every displayed metric must come from one backend source of truth.
7. Use shared UI components for scores, metrics, status, risk, and freshness.
8. Do not create backend APIs solely around React component needs.
9. Preserve working behavior during migration.
10. Remove legacy logic only after replacement behavior is verified.

---

# 36. Modular Monolith First

The preferred architecture is a **modular monolith**.

Do not create microservices yet.

Benefits:

- simpler local development,
- faster iteration,
- easier debugging,
- easier AI-agent reasoning,
- fewer deployment concerns,
- shared domain transactions,
- future service extraction remains possible.

Strong internal boundaries matter more than distributed deployment right now.

---

# 37. Recommended Technology Direction

```text
Frontend:
React

API:
FastAPI

Domain / Quant:
Python

Configuration:
Typed settings + versioned config

Persistence:
Relational database for durable state

Cache:
Existing centralized cache initially

Background work:
Lightweight job abstraction

Tests:
pytest + API + frontend + contract tests
```

Use the simplest infrastructure that supports the required behavior.

---

# 38. Migration Order

## Phase 1 — Foundation

- canonical indicators,
- typed configuration,
- shared domain models,
- provider abstractions,
- data freshness metadata.

## Phase 2 — Market Intelligence

- market regime,
- structure,
- relative strength,
- volatility,
- shared market snapshot.

## Phase 3 — Options Scanner

- hard vetoes,
- Direction Engine,
- Volatility Engine,
- QX Opportunity Score,
- Strategy Selector,
- Trade Construction,
- Risk,
- lightweight telemetry,
- Scanner UI.

## Phase 4 — Research

Rebuild Research to consume the same Market Intelligence services.

## Phase 5 — Position Management

Replace hard-rule-only advisor with Position Health architecture.

## Phase 6 — Strategy Workspaces

Migrate:

- SPX Calendars,
- LEAPS,
- PMCC,
- Wheel,
- credit/debit spread workspaces.

## Phase 7 — Integrations

Add as needed:

- better market-data providers,
- broker account/position integration,
- alerts,
- richer AI,
- options flow,
- GEX,
- dark pool,
- additional data sources.

---

# 39. Deferred Features

Do not block the rebuild on:

- paper trading,
- backtesting,
- large historical databases,
- options tick replay,
- historical chain warehousing,
- ML scoring,
- automated execution,
- full Kelly sizing,
- paid GEX,
- dark-pool feeds,
- Unusual Whales-style flow,
- microservices,
- Kafka,
- distributed infrastructure.

The architecture should allow future integration without depending on these now.

---

# 40. Anti-Patterns

The AI coding agent must not:

1. Put trading calculations in React.
2. Duplicate indicators.
3. Couple scanner directly to one market-data vendor.
4. Duplicate Greeks or option logic by strategy.
5. Convert all factors into binary gates.
6. Scatter thresholds across multiple files.
7. Mix Scanner and Position Advisor rules.
8. Use the LLM as the deterministic source of truth.
9. Hide market-data failures.
10. Display stale cached data as live.
11. Create a separate architecture per page.
12. Introduce microservices prematurely.
13. Add backtesting or paper-trading infrastructure.
14. Introduce large historical data stores.
15. Rewrite working QX structure logic unnecessarily.
16. Refactor multiple unrelated layers in one uncontrolled change.
17. Mark a module complete without tests.

---

# 41. AI Agent Working Protocol

For every migration task:

## Step 1 — Inspect

Identify:

- existing page,
- current APIs,
- current calculations,
- current data source,
- duplicate logic,
- tests.

## Step 2 — Classify

Classify each behavior as:

```text
UI
Application
Domain
Provider
Persistence
Configuration
Telemetry
```

## Step 3 — Extract

Move reusable logic into the appropriate QX domain.

## Step 4 — Contract

Create typed input/output models.

## Step 5 — Adapt

Connect external data through provider abstraction.

## Step 6 — Rebuild UI

Make React consume the typed API response.

## Step 7 — Test

Add unit, integration, regression, and API tests.

## Step 8 — Compare

Verify new behavior against known working behavior.

## Step 9 — Remove Legacy

Remove duplicate legacy code only after parity is verified.

---

# 42. Current Priority

Do not add more pages first.

Recommended order:

1. Establish QX Core boundaries.
2. Establish canonical indicators.
3. Establish typed market snapshot.
4. Establish provider abstraction.
5. Rebuild Options Scanner.
6. Rebuild Research using the same core services.
7. Rebuild Position Advisor using Position Health.
8. Preserve SPX Calendar as a specialized strategy module.
9. Add integrations and alerts as required.

---

# 43. Approved Architecture Decisions

```text
Architecture:
MODULAR MONOLITH

Frontend:
REACT

API:
FASTAPI

Primary Quant Language:
PYTHON

Trading Logic in Frontend:
PROHIBITED

Shared Calculations:
REQUIRED

Scanner vs Position Advisor:
SEPARATE DOMAINS

Strategy Logic:
MODULAR

Market Data:
PROVIDER ABSTRACTION

Broker:
PROVIDER ABSTRACTION

AI:
EXPLANATION / ASSISTANCE LAYER

AI as Trading Source of Truth:
PROHIBITED

Telemetry:
LIGHTWEIGHT ONLY

Paper Trading:
NOT INCLUDED

Backtesting:
NOT INCLUDED

Large Historical Data Stores:
NOT INCLUDED

Microservices:
DEFERRED

Machine Learning:
DEFERRED

Automated Live Execution:
DEFERRED

Thresholds:
CENTRAL CONFIG

Scoring:
VERSIONED

Metrics:
ONE SOURCE OF TRUTH

Data Freshness:
MANDATORY

Migration:
INCREMENTAL
```

---

# 44. Final Instruction to the AI Coding Agent

Treat this document as the QX platform architecture source of truth.

Do not rewrite the entire system at once.

For every change:

1. inspect existing working behavior,
2. identify the correct domain,
3. preserve working QX logic,
4. extract reusable calculations,
5. introduce typed contracts,
6. use provider abstractions,
7. keep pages thin,
8. keep Scanner and Position Management separate,
9. centralize configuration,
10. preserve data freshness,
11. add tests,
12. remove legacy logic only after replacement is verified.

The goal is to create a platform that supports current needs and future additions such as:

- stronger Options Scanner logic,
- SPX strategy modules,
- Futures,
- LEAPS,
- PMCC,
- Wheel,
- portfolio management,
- broker integration,
- alerts,
- better market-data feeds,
- richer AI agents,
- and eventual execution support,

without requiring another major architectural rewrite.

**Build future integrations as additions to the architecture, not as reasons to replace the architecture.**
