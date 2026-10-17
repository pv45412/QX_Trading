# QX Two-Page Trading Workspace — Architecture & Implementation Plan

Status: **PROPOSED — awaiting approval** · Author: QX product architect / qx-orchestrator
Scope change: supersedes the scanner-only brief by adding **human-confirmed Schwab trade execution**.
Governance: this document is a *design artifact*. Per `QX_ROADMAP.md` / `QX_BACKLOG.md`, a design document does
**not** authorize implementation, and broker writes require the EX0→EX1→EX2→EX3 human gates.

---

## 1. Audit — what already exists (verified in-repo)

The repository already contains a substantial deterministic engine. **Do not rebuild these.**

### 1.1 Deterministic decision engine (Python)
| Capability | Location | State |
|---|---|---|
| Playbooks A/B/C (pullback, liquidity sweep, ORB) with `playbook_id`, `playbook_version`, `state ∈ {ARMED, WATCH, NO_SETUP}` | `src/qx/playbooks/{engine,base,pullback,liquidity_sweep,orb,context}.py` | EXISTS |
| Trigger engine → `TriggeredSetupResult` (`state=TRIGGERED`, trigger/invalidation/target) | `src/qx/triggers/{engine,models}.py` | EXISTS |
| Tradeability gates (max delay bars, max extension ATR, max gap distance ATR, **min risk/reward**, min participation + evidence coverage) | `src/qx/tradeability/{engine,models}.py` | EXISTS |
| Canonical opportunity service + SQLite persistence (repository, migrations, publisher) | `src/qx/opportunities/` | EXISTS (BE1 COMPLETE) |
| Deterministic pipeline + stage latencies + `armed_playbook` + engine versions | `src/qx/pipeline/orchestrator.py`, `models.py` | EXISTS |
| Publication / execution-eligibility state | `src/qx/models/publication.py` | EXISTS |
| HARD/SOFT gate kinds | `src/qx/models/rules.py` | EXISTS |
| All playbook thresholds, DTE windows, participation config | `src/qx/config/rules_config.py` | EXISTS |
| Watchlist `setup_state` | `src/qx/watchlist/engine.py` (`_setup_state`) | EXISTS |
| Sector normalization (canonical sector ids), allocations, greeks risk | `src/qx/portfolio/{sectors,greeks_risk,models}.py` | EXISTS |
| Market Driver engine | MD1/MD2 (COMPLETE per `PROJECT_STATE.md`) | EXISTS |

### 1.2 Execution layer — **paper/simulation only**
`src/qx/execution/` contains `order_router.py`, `bracket_manager.py`, `reconciliation.py`, `lifecycle.py`, `pipeline.py`, `models.py`.
- `OrderRouter` is an **in-memory smart order router + paper execution engine**: `submit_order`, `execute_fill`, `cancel_order`, `list_orders`.
- It already enforces a **fail-closed eligibility rule**: order proposals are rejected unless `publication_state == "VERIFIED"` **and** `executable is True` (`validate_execution_eligibility`).
- `OrderStatus` already models `SUBMITTED / FILLED / PARTIALLY_FILLED / CANCELED / REJECTED`; `ExecutionFill` models fills.
- **No Schwab order submission exists.** No `POST /trader/v1/.../orders` anywhere in the repo.

### 1.3 Schwab integration (`src/qx/brokers/schwab/`)
`auth.py` (OAuth token manager + refresh), `client.py`, `config.py`, `health.py`, `market_data.py`, `movers.py`, `options.py`, `quotes.py`, `symbols.py`, `timing.py`, `accounts.py`.
- `accounts.py` is explicitly **read-only**: `SchwabReadOnlyAccountSnapshotProvider`, `read_only=True`, `publication_state="RESEARCH_ONLY"`. It reads `GET /trader/v1/accounts?fields=positions` and `GET /trader/v1/accounts/{hash}/orders`.
- Credential/OAuth control surface is local-only: `src/qx/interfaces/schwab_system.py` (403 unless same-origin/local).

### 1.4 Frontend (React 19 + Vite 6, no component library)
Stack: `react`, `react-dom`, `recharts`, `lucide-react`; plain CSS (`style.css`, `dashboard.css`, `QXDayTraderTerminal.css`).
Existing surfaces: `QXInstitutionalScanner.jsx`, `QXOpportunitiesWorkspace.jsx`, `QXTradeWorkspace.jsx`, `QXPortfolioWorkspace.jsx`,
`QXResearchWorkspace.jsx`, `QXSystemControl.jsx`, `QXTodayWorkspace.jsx`, `QXMarketDriverPanel.jsx`, `QXLifecyclePanel.jsx`,
`QXDataEvidence.jsx`, `QXOptionsScanner.jsx`, `ReferenceRanking.jsx`, `RSLine.jsx`, `WorkspaceNavigation.jsx`, `workspace-routes.js`.
Existing model/client layers (reusable seams): `qx-opportunities-{client,model}.js`, `qx-trade-workspace-model.js`, `qx-v2-{adapter,client,feature}.js`,
`qx-portfolio-*`, `qx-research-*`, `qx-system-*`, `qx-today-*`, `qx-market-quotes-client.js`, `schwab-credentials-client.js`, `workspace-context.js`.
**There is already an 8-tab navigation; the brief asks for exactly two primary items.**

### 1.5 Harness surfaces already built this session (verified active)
- DSH plugin `@qx/schwab-plugin` (installed, enabled, applied): tools `qx_schwab_status|scan|alerts|confirm_trade|auth_url|authorize`; skills `schwab-rules-engine`, `schwab-trade-desk`, `schwab-alert-monitor`; dashboard `/qx/schwab`; paper-only `confirm_trade` (fail-closed).
- Workspace skills under `.agents/skills/` (e.g. `smc-rules-engine/resources/qx_rules_engine_spec.md` + 12 `.tos` studies, `fastapi-backend-routes`, `react-dashboard-design`).

---

## 2. Verified integration capabilities

### 2.1 Verified working (exercised live this session)
| Capability | Evidence |
|---|---|
| OAuth authorization-code + refresh lifecycle | token exchange completed; `SchwabTokenManager.status()` → token ready |
| Realtime-ish quotes | `GET /marketdata/v1/quotes` → SPY last 779.88, `realtime=True` |
| Daily price history | `GET /marketdata/v1/pricehistory` → 500 bars |
| Read-only accounts + positions | `GET /trader/v1/accounts?fields=positions` (used by `accounts.py`) |
| Read-only order listing | `GET /trader/v1/accounts/{accountHash}/orders` (count/status only) |

### 2.2 NOT verified — must be treated as unverified
| Question | Status |
|---|---|
| `POST /trader/v1/accounts/{accountHash}/orders` order placement | **UNVERIFIED** (no code path; docs unreachable) |
| Order **preview** endpoint | **UNVERIFIED** — do not assume it exists |
| Schwab **paper/sandbox** environment | **UNVERIFIED** — do not assume one exists |
| Equity/option order structure matrix vs account permissions | **UNVERIFIED** |
| Idempotency keys / duplicate suppression at broker | **UNVERIFIED** — assume none |
| Whether the current OAuth app carries **trading** product approval | **UNVERIFIED** |

### 2.3 Blockers preventing that verification *right now*
1. **Web search is down** — the search endpoint returns `HTTP 402 Insufficient Balance` (request routed to `api.deepseek.com/anthropic/v1/messages`). No web research possible until the user fixes the search endpoint/credits (Settings ▸ Plugins ▸ Web search).
2. **Schwab developer docs are unreachable** — `web_fetch` of `developer.schwab.com/products/trader-api--individual/details/documentation` returns `HTTP 403 Access Denied` (edge-protected; requires an authenticated session).
3. Therefore the order-structure matrix **must** be confirmed by the user inside their authenticated Schwab developer portal, or by a separately authorized live test — per the brief ("Report any broker behavior that remains unverified without a separately authorized live test").

---

## 3. Blockers / constraints (product + governance)

| # | Blocker | Impact | Resolution |
|---|---|---|---|
| B1 | **Governance: broker writes prohibited** (`QX_ROADMAP.md`, `QX_BACKLOG.md`, `PROJECT_STATE.md`). EX0→EX1→EX2→EX3 each need human review; EX3 needs explicit live-trading authorization; "a recommendation or design document does not authorize implementation." | Phase 5 (live submission) cannot be implemented without approval. | Treat this plan as the **EX0-class execution-readiness design**; get explicit approval to open EX1/EX2. |
| B2 | Only one milestone may be `READY` (currently PERF2). | New work needs an approved milestone contract. | Human approves a new contract (e.g. `UX7`/`EX0`) before code. |
| B3 | Schwab order API/paper env **unverified** (§2.2). | Cannot promise preview, sandbox, or exact order payloads. | Ship **local validation + application-level simulated trading** as the default; gate live. |
| B4 | Web search + Schwab docs unreachable (§2.3). | Research-dependent work is blocked. | User fixes search endpoint / confirms docs in-portal. |
| B5 | No broker idempotency guarantee assumed. | Duplicate submissions possible on retry/reconnect. | Client-side submission lock + intent ledger + reconcile-before-retry (§5.4). |
| B6 | Secrets discipline: tokens must never reach the browser, AI prompts, or logs. | Any browser-side order call is forbidden. | All broker calls go through the Python backend adapter; browser gets only sanitized state. |
| B7 | Frontend has no component library / design tokens shared with the React app. | Two-page redesign needs a small token + primitives layer. | Add a minimal CSS-variable token layer + 4 primitives; no new heavy deps. |
| B8 | Live-data/UI plumbing friction observed this session (DSH plugin module cache requires restart; `qx_schwab_*` tools already exist). | Some Harness-side changes need a DSH restart. | Keep the canonical engine in the QX backend; DSH plugin remains a thin client. |

---

## 4. Proposed two-page layout

Two primary navigation items only. All other existing workspaces move under a secondary "More" menu (or are retired) — **no page is deleted until its replacement is verified** (per backlog rules).

```
┌ QX ────────────────────────────────────────────────────────────────────────────┐
│  [ Scanner ]  [ Trade Workspace ]                              ● live · 14:32:07 │
└────────────────────────────────────────────────────────────────────────────────┘
```

### PAGE 1 — Scanner
Fast, dense, keyboard-first. Purpose: **find and qualify** setups.

```
┌ MARKET CONTEXT ──────────────────────────────────────── data as of 14:31:58 · FRESH ┐
│ Regime: RISK-ON   Breadth: 68%   11/11 sectors ranked   Coverage: R1000 declared    │
│ [STALE] banner replaces status when any input exceeds its freshness budget          │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ SECTOR RANKINGS (11/11) ────────────────────────────────────────────────────────────┐
│ #  Sector            RS 5d   RS 20d   RS 60d   Quadrant   Coverage                  │
│ 1  Technology        +2.1%   +5.4%    +8.9%    LEADING    R1000 ✓                  │
│ …  all 11 declared sectors, never a partial list without an explicit "coverage" note │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ RESULTS ── [Intraday | Swing] ──────────────────────────────────────────────────────┐
│ Filters: Sector ▾  Instrument ▾  Playbook ▾  Timeframe ▾  Setup state ▾            │
│ ┌ Rank ─ Bullish (n) ─────────────────────────────────────────────────────────────┐ │
│ │ ▸ 1  NVDA  LONG  A-pullback  15m  EXECUTABLE  score 78.9  R:R 2.6  ▸ expand     │ │
│ │ ▸ 2  MSFT  LONG  C-orb       5m   ARMED       score 71.2  R:R 2.1  ▸ expand     │ │
│ └─────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ Rank ─ Bearish (n) ─────────────────────────────────────────────────────────────┐ │
│ │ ▸ 1  XLE   SHORT B-sweep     30m  TRIGGERED   score 68.0  R:R 1.9  ▸ expand     │ │
│ └─────────────────────────────────────────────────────────────────────────────────┘ │
│  expanded row → score breakdown · risk/reward · passed gates · rejection reasons    │
│  empty → "NO_QUALIFIED_TRADE" (never a forced recommendation)                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ SETUP DETAIL (resizable split) ─────────┬─ AI TRADE NOTES ▸ (collapsible drawer) ──┐
│ chart: entry · invalidation · targets   │ 1 Why it qualifies                       │
│ legend + price axis + timeframe         │ 2 Market & sector alignment              │
│                                         │ 3 Entry conditions & invalidation        │
│ [ Open Trade Workspace → ]  ← carries   │ 4 Targets & management scenarios         │
│    setup_id + version snapshot forward  │ 5 Conflicting evidence & event risks     │
└─────────────────────────────────────────┴──────────────────────────────────────────┘
```

Contracts:
- **`NO_QUALIFIED_TRADE`** is a first-class result when nothing passes every gate.
- Every number carries its **as-of timestamp** and **evidence reference**; stale inputs visibly mark the row.
- Filters are deterministic projections over the same result set (no re-scoring in the UI).
- Results are virtualized; charts lazy-load on selection.

### PAGE 2 — Trade Workspace
Purpose: **act on exactly one carried-forward setup**, safely.

```
┌ CONNECTION ─────────────────────────────────────────────────────────────────────────┐
│ Schwab: CONNECTED · token valid · [account selector ▾] ••••1234  (MARGIN)           │
│   DISCONNECTED → all order actions disabled, read-only cache shown with STALE tag   │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ ACCOUNT ────────────────────────────┬─ SELECTED SETUP ──────────────────────────────┐
│ Equity / Cash / Buying power        │ setup_id 8f3a…  v3 (snapshot 14:31:58)        │
│ Positions (qty, px, uPnL)           │ NVDA LONG  A-pullback 15m  EXECUTABLE         │
│ Open orders (status, id, remaining) │ entry 182.40  invalidation 178.10  R:R 2.6    │
│ unsupported → "not provided by API" │ chart + live quote (as-of stamp)              │
└─────────────────────────────────────┴───────────────────────────────────────────────┘
┌ ORDER TICKET (prefilled, editable) ─────────────────────────────────────────────────┐
│ Structure [Equity | Single option | Vertical | …]   ← capability-gated, verified set │
│ Symbol NVDA   Side BUY   Qty 100   Type LIMIT   Price 182.40   TIF DAY              │
│ Est. cost $18,240   Risk to invalidation $430 (2.4R)   Max loss (defined)            │
│ ⚠ changing account/instrument/side/qty/price INVALIDATES the confirmation below      │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ REVIEW (local) ─────────────────────────────────────────────────────────────────────┐
│ Exact proposed order, verbatim payload preview (sanitized), risk summary             │
│ Mode: [ SIMULATED ]  or  [ LIVE ]   ← unmistakable, persistent, colour+label         │
│ [ Request confirmation ] → challenge → [ CONFIRM SUBMIT ] (enabled ≤ 15s)            │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ SUBMISSION ─────────────────────────────────────────────────────────────────────────┐
│ intent 9c1e… · SUBMITTING… → ACK orderId 1000…  → WORKING → PARTIAL 40/100 → FILLED  │
│ REJECTED: <broker reason verbatim>   CANCELED   EXPIRED   (all states shown)         │
│ [ Cancel order ]   [ Reconcile ]   ← shown only where supported                      │
│ timeout/unknown → "UNCERTAIN — reconciling with broker records" (never blind retry)  │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ MANAGE ─────────────────────────────────────────────────────────────────────────────┐
│ only recorded FILLS move the setup to MANAGE; positions/orders re-reconciled on reconnect │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Shared data model

One **setup identity** threads scanner → notes → ticket → broker order → fill → outcome.

### 5.1 Setup identity & snapshots
```
SetupId            = stable deterministic hash(playbook_id, symbol, timeframe, direction, session_anchor)
SetupVersion       = monotonically increasing integer per SetupId
SetupSnapshot      = { setup_id, version, captured_at, engine_versions{}, inputs_hashes{},
                       state, score, factors{}, gates[], rejection_reasons[],
                       entry, invalidation, targets[], risk_reward, evidence_refs[] }
```
- The **original plan is immutable**: later re-evaluations create a new `SetupVersion` + new snapshot; the UI can always diff *original vs current*.
- `evidence_refs[]` point at stored scanner evidence (quote/bars as-of, playbook evaluation, trigger, tradeability gates, market driver, sector rank) so AI notes can cite real values.

### 5.2 QX setup states (engine-owned, preserved)
```
WATCH → ARMED → TRIGGERED → EXECUTABLE → MANAGE → EXIT
```
Mapped onto existing engine outputs (`playbooks.state` ARMED/WATCH/NO_SETUP → `triggers` TRIGGERED → `tradeability` gates → EXECUTABLE; EXECUTABLE requires `publication_state == VERIFIED` and `executable == True`).

### 5.3 Broker order states (separate namespace — never conflated)
```
DRAFT → CONFIRMED_LOCAL → SUBMITTING → ACK/WORKING → PARTIAL → FILLED
                                       ↘ REJECTED ↘ CANCELED ↘ EXPIRED ↘ REPLACED
                                       ↘ UNCERTAIN (timeout, result unknown)
```
**Invariant:** `EXECUTABLE (setup)` ≠ `SUBMITTED (order)` ≠ `FILLED (fill)`. A recorded fill is the only thing that advances a setup to `MANAGE`.

### 5.4 Order intent ledger (duplicate-submission defence)
```
OrderIntent = { intent_id, setup_id, setup_version, ticket_hash, mode: SIMULATED|LIVE,
                state, created_at, confirmation_id, broker_order_id?, reconciled_at? }
```
- `ticket_hash` = hash(account_id, symbol, structure, side, qty, order_type, price, tif).
- A submit is refused if an `OrderIntent` with the same `ticket_hash` is in a non-terminal state (blocks double-click, retry, reconnect, page refresh).
- Any edit changes `ticket_hash` → the previous confirmation is void and a new one is required.
- `UNCERTAIN` intents are **reconciled against broker records before any retry** (no idempotency assumption).

### 5.5 AI notes model
```
TradeNote = { note_id, setup_id, setup_version, sections{1..7}, generated_at,
              evidence_refs[], rule_versions{}, staleness: FRESH|STALE, stale_reason? }
```
Sections: 1 why it qualifies · 2 market/sector alignment · 3 entry & invalidation · 4 targets & management · 5 conflicting evidence & event risk · 6 what changed since previous review · 7 post-trade review.
Notes become `STALE` when any underlying evidence hash or rule version changes.

---

## 6. Reusable existing components (build on, don't replace)

| Need | Reuse |
|---|---|
| Setup/playbook/trigger/tradeability decisions | `src/qx/playbooks`, `triggers`, `tradeability` |
| Canonical opportunity contract + persistence | `src/qx/opportunities/` (BE1) |
| Deterministic pipeline + versions/latencies | `src/qx/pipeline/orchestrator.py` |
| Paper order lifecycle, fills, brackets, reconciliation | `src/qx/execution/{order_router,bracket_manager,reconciliation,lifecycle,models}.py` |
| Fail-closed eligibility rule | `OrderRouter.validate_execution_eligibility` |
| Schwab auth/client/market data | `src/qx/brokers/schwab/{auth,client,market_data,quotes,options}.py` |
| Read-only account/positions/orders | `src/qx/brokers/schwab/accounts.py` |
| Credential/OAuth control surface | `src/qx/interfaces/schwab_system.py` |
| Sector normalization + RS ranks | `src/qx/portfolio/sectors.py`, market driver panels |
| Frontend data seams | `qx-opportunities-{client,model}.js`, `qx-trade-workspace-model.js`, `qx-market-quotes-client.js`, `qx-v2-adapter.js`, `workspace-context.js` |
| Frontend surfaces to consolidate | `QXInstitutionalScanner.jsx`, `QXOpportunitiesWorkspace.jsx`, `QXTradeWorkspace.jsx`, `QXMarketDriverPanel.jsx`, `QXLifecyclePanel.jsx`, `QXDataEvidence.jsx`, `RSLine.jsx` |
| Charts | `recharts` (already present) |
| Navigation/routing | `WorkspaceNavigation.jsx`, `workspace-routes.js` |

New pieces to add (small): CSS design tokens + 4 primitives (Table, Drawer, StatusChip, SplitPane); `qx-setup-model.js`; backend `execution/broker_adapter.py` + `order_intent_store.py`; AI notes service.

---

## 7. Phased implementation plan

Each phase ends at a gate; no phase silently expands scope.

### Phase 0 — Approval & contracts (gate)
- Human approves this design and opens a milestone contract (`tasks/UX7_TWO_PAGE_WORKSPACE.md` + the EX0 execution-readiness design).
- Deliverable: approved contract, EX0 design doc, kept in `tasks/`.
- **Gate:** explicit human approval. Nothing below starts before it.

### Phase 1 — Audit consolidation & data foundation
- Freeze the setup identity/version/snapshot model; add `qx-setup-model.js` + backend snapshot serializer.
- Wire freshness/as-of + evidence references into the existing pipeline output (read-only).
- Contract tests: same inputs ⇒ identical scores (reproducibility).
- **Acceptance:** scanner results reproduce from the same inputs.

### Phase 2 — Scanner vertical slice (deterministic)
- Two-page nav shell; Scanner page with market context, 11/11 sector rankings + declared coverage, intraday/swing split, bullish/bearish rankings, filters, virtualized table, expandable details, score breakdown, R:R, passed gates, rejection reasons.
- `NO_QUALIFIED_TRADE` path; explicit stale/disconnected/empty/error states.
- Selected-setup chart (entry/invalidation/targets) + **Open Trade Workspace** carrying `setup_id` + snapshot.
- **Gate:** UI preview loop artifacts (`tasks/UI_PREVIEW_LOOP.md`); deterministic reproduction verified.
- **Acceptance:** opening a setup preserves plan + identity across pages; stale data visibly blocks qualification.

### Phase 3 — Evidence-linked AI trade notes
- Notes service generating sections 1–6 from stored evidence + timestamps + rule versions; staleness on evidence/rule change; commands (explain / invalidate / compare / update-plan / explain-risk / review-trade).
- AI is read-only over deterministic services: it may explain and *draft* proposed changes; applying a ticket change requires explicit user action + renewed confirmation.
- **Acceptance:** notes cite actual values; they go STALE when evidence changes.

### Phase 4 — Trade Workspace with simulated orders + broker read-only
- Connection status + identified account; balances/buying power/positions/open orders (mark "not provided" where the API lacks it).
- Prefilled editable ticket; supported structures limited to a verified capability set; est. cost + risk.
- Local review + verbatim sanitized payload preview; **SIMULATED** mode wired to `OrderRouter`; intent ledger with duplicate-submission lock; reconciliation path.
- **Acceptance:** repeated clicks cannot double-submit; rejected/cancelled/partial states display accurately; simulated vs live unmistakable.

### Phase 5 — Human-confirmed LIVE submission + reconciliation (⚠ gated)
- New `execution/broker_adapter.py` (backend-only): order build → local validation → confirmation challenge → submit via `POST /trader/v1/accounts/{accountHash}/orders`.
- Tokens stay server-side; browser never sees a token; AI prompts/logs never carry secrets.
- Refresh quotes + account checks immediately before submission; any ticket edit invalidates confirmation.
- Timeout ⇒ `UNCERTAIN` ⇒ reconcile via order history before retry; fills drive `MANAGE`; positions/orders reconciled on reconnect.
- **Gate:** requires EX1 (eligibility semantics), EX2 (paper), EX3 (live authorization) approvals + verified kill/rollback. Order payload/structures must be confirmed against authenticated Schwab docs or a separately authorized live test — otherwise remain UNVERIFIED and keep LIVE disabled.
- **Acceptance:** no live trade without explicit confirmation; unknown outcomes reconcile; credentials protected.

### Phase 6 — Verification, failure handling, performance
- Failure matrix tests (disconnect mid-submit, partial fill, reject, cancel, stale data, duplicate intent, restart).
- Performance: virtualized results, lazy charts, incremental updates, measured scanner latency.
- Independent review roles: builder, architecture reviewer, quant/semantics reviewer, QA gatekeeper (maker never self-approves).

---

## 8. Acceptance criteria → verification map

| Criterion | Verified by |
|---|---|
| Scanner results reproduce from same inputs | Phase 1 contract tests (deterministic replay) |
| Missing/stale data blocks execution eligibility | Phase 2 stale states + Phase 4 eligibility gate |
| Opening a setup preserves plan + identity across pages | Phase 2 setup_id/version carry test |
| AI notes reference real evidence; go stale | Phase 3 evidence-ref + staleness tests |
| Simulated vs live unmistakable | Phase 4 persistent mode banner + tests |
| Repeated clicks cannot duplicate submissions | Phase 4 intent-ledger tests |
| Unknown submission outcome triggers reconciliation | Phase 4/5 `UNCERTAIN` → reconcile tests |
| Rejected/cancelled/partial display accurately | Phase 4 state-rendering tests |
| Broker fills + positions drive management status | Phase 5 fill→MANAGE + reconnect reconcile |
| Credentials protected (off browser/prompts/logs) | Phase 5 secret-leak tests |
| No live trade without explicit confirmation | Phase 5 confirmation-challenge tests |

---

## 9. Immediate next step

**Blocked on your decision.** To proceed I need:
1. Approval of this design + a milestone contract (Phase 0 gate) — and confirmation that the **scanning/UI phases (1–4)** may proceed while **Phase 5 stays gated** behind EX1–EX3.
2. A fix for the **web-search endpoint** (HTTP 402) if you want Schwab order documentation verified from here; otherwise confirm the order capability matrix yourself in the authenticated Schwab portal.
3. Confirmation of the **account/product approval** the OAuth app currently carries (market data only vs trading).
