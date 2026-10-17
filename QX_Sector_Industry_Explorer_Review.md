# Sector & Industry Explorer — Design Review & Refined Plan

Status: **REVIEW FIRST — awaiting your decision. No code written yet.**
Prepared after inspecting the existing implementation, per your instruction.

---

## Part A — What I verified before proposing anything

### A1. There is **no** Momo/Trend study in this repo

You asked me to locate the real study behind your Momo/Trend labels. I searched the
workspace. Result:

- The 12 `.tos` studies in `.agents/skills/smc-rules-engine/resources/` are **SMC / auction /
  CVD / VSCORE / ORB / RS-percentile** studies. **None** computes a "Momo" or "Trend" state.
- Grepping every `.tos` for `Momo|Momentum|TrendUp` matched **only**
  `tos_rs_percentile_rank.tos` — and that is a *relative-strength percentile* study, not a
  Momo/Trend state machine.
- No entry in `src/qx/**` produces `momentum_up` / `trend_up` / `alignment` states. The grep
  hits were unrelated words in rules docs and a `.phase8-backup` copy.

**Consequence:** I cannot claim parity with your screenshot, and I will not. Requirement 3
resolves to the fallback branch: implement a **separately named, versioned baseline**
(`qx_momo_trend_v1`) that never claims to reproduce the screenshot. If you can export the
actual ThinkScript for those two labels, I will port it and test parity instead.

### A2. Holdings and membership infrastructure **does** exist — and is unusually careful

This is the good news; two genuinely distinct universes are buildable.

| Piece | Location | Real behaviour |
|---|---|---|
| ETF holdings provider | `src/qx/data/holdings.py` | Yahoo `funds_data.top_holdings` — **top 10 only**, with weights; `holdings_as_of` is `None` (retrieval time is *explicitly* not the holdings date) |
| Saved/cached holdings | same | `saved_top_holdings` **never re-dates**; returns `stale_holdings: True`, `holdings_status: SAVED_UNVERIFIED` |
| Holdings integrity | `_validate_holdings` | rejects duplicate tickers, non-finite or out-of-range weights, `total > 1.001`, future timestamps |
| Classified members | `src/qx/data/membership.py` | CSV symbol lists with **content-bound provenance**: `sha256` digest bound to a `.meta.json`, `official: False`, `effective_date: None` |
| Membership safety | `validate_membership_change` | rejects >10% membership churn as "source review required" |
| Universe loader | `src/qx/data/universe.py` | sp500 / sp100 / dow_jones / nasdaq_100 / russell_2000, cached, 24h TTL |

Both modules deliberately refuse to pretend retrieval time is an effective date. **My
explorer must inherit that discipline, not paper over it.**

### A3. What exists to reuse for alignment, breadth and entry quality

- `src/qx/scanner/studies.py` — EMA/RSI/MACD/ATR/VWAP-σ, factor scoring, `RULE_VERSION`.
  **Has `ema()` already** → the baseline's EMA20/EMA50 needs no new indicator code.
- `src/qx/market/sector_rotation.py`, `holding_analytics.py` — sector rotation and holding
  enrichment already exist.
- `src/qx/playbooks/` (A pullback / B liquidity sweep / C ORB), `triggers/`, `tradeability/`
  (min R:R, extension ATR, gap ATR, participation) — **the existing validated playbooks**
  requirement 5 says to use. They already emit playbook id, structural levels, trigger,
  invalidation, and gate reasons.
- `src/qx/execution/order_router.py::validate_execution_eligibility` — the fail-closed
  `VERIFIED + executable` gate my Trade Workspace already reports honestly.

### A4. Two hard blockers

1. **Holdings are top-10 only.** Yahoo's `top_holdings` gives ~10 rows. A sector explorer
   whose breadth denominator is 10 mega-caps is **actively misleading** — it cannot
   distinguish "broad participation" from "a few large holdings", which is precisely your
   requirement 4. So: **Universe A (ETF Holdings) is partial by construction**, and the UI
   must say so loudly. Real breadth needs `Universe B` (classified members) with a genuine
   constituent list.
2. **No SMH/industry constituent list is present on disk.** I found only index universes
   (sp500/nasdaq_100/…). Industry ETFs like **SMH** need a *classified constituent* source.
   `universe.py` can parse `stockanalysis_holdings_symbols` HTML, so a provider is feasible —
   but it is **unverified**, and until it is wired and tested I must show
   `MEMBERSHIP_UNAVAILABLE` with the last known date rather than fabricate a list.

---

## Part B — Refinements I propose (and where I push back)

I agree with most of the brief. Six changes I'd make, with reasons.

### B1. `Universe A` should be labelled "Reported Top Holdings", not "Holdings"

Because it is top-10. Calling it "Holdings" implies completeness and would make every breadth
number a lie. Proposed labels, kept permanently distinct in the data contract **and** the UI:

- `ETF_REPORTED_TOP_HOLDINGS` — weights available, ~10 rows, **partial**, `holdings_as_of: unknown`
- `CLASSIFIED_MEMBERS` — full classified constituents, **no weights**, provenance-bound

`universe` is a required field on every row and every breadth number. A switch between them is
an explicit user action; neither is ever silently substituted for the other.

### B2. Breadth gets an explicit `denominator` object, and a "top-10 skew" warning

Your requirement 4 is the sharpest part of the brief. I'd make it structural:

```
breadth: {
  universe: "CLASSIFIED_MEMBERS",
  eligible_members: 62,        // after warmup + data + liquidity
  covered_members: 58,         // with usable history
  missing_data: 4,
  trend_up_pct: 0.53,
  aligned_pct: 0.31,
  breadth_change_since_previous_scan: +0.06,
  equal_weight: true,          // or false when weights exist
  weight_covered_pct: 0.42,    // A-universe only; how much of the fund the covered rows represent
  denominator_note: "62 eligible; 4 excluded for insufficient history"
}
```

Critically: **breadth is computed over the eligible covered universe *before* display
filters** (your requirement), and when `universe == ETF_REPORTED_TOP_HOLDINGS` the UI shows a
persistent `TOP_10_ONLY — not sector breadth` badge. Without that, a 10-name sample reads as a
sector verdict.

### B3. Alignment must be provably unable to reach `EXECUTABLE`

You already state this, but I want it enforced in the type system, not by convention:

- The explorer emits `alignment_state ∈ {UP, DOWN, MIXED, UNKNOWN}` and
  `entry_readiness ∈ {PULLBACK_CANDIDATE, BREAKOUT_WATCH, TRIGGER_CONFIRMED, EXTENDED_WAIT,
  BLOCKED_*}`.
- `setup_state` is **derived only** from the existing playbook/tradeability pipeline.
- `EXECUTABLE` requires `publication_state == VERIFIED && executable is True` — the repo's own
  gate, which the explorer **cannot** set. Momo+Trend UP can produce at most
  `TRIGGER_CONFIRMED`, never `EXECUTABLE`, and never a `BUY CALL`/`BUY PUT` recommendation.
- I'd add a test that asserts `alignment == UP/UP` **and** no playbook ⇒ `setup_state != EXECUTABLE`.

### B4. Momentum baseline: I'd tighten the proposed rule

Your proposed `Momentum UP = positive 5-bar ROC and positive change in that ROC` is a
**second-derivative** rule and will be very noisy on daily bars — it flips easily and will
flicker. My proposed refinement (still a *baseline*, still configurable):

- `MOMENTUM_UP` = `ROC(5) > +neutral_band` **and** `ROC(5) > ROC(5)[roc_lookback]`
- `MOMENTUM_DOWN` = symmetric inverse
- else `MIXED`, with `neutral_band` default `0.0` (explicit, not implied)
- `confirmation_bars` default `2` — a state must persist N completed bars before being
  published as a *transition* (not before being displayed)

And per your instruction, I will **validate** that longer confirmation is not automatically
better rather than assume it: the verification step measures label-flip counts and lag across
`confirmation_bars ∈ {1,2,3}` and reports the trade-off, so the default is evidence-chosen.

### B5. Two new states I think the brief is missing

- `STALE_QUOTE` — price older than its freshness budget. Alignment computed on stale bars must
  be shown as stale, not as a live signal.
- `INSUFFICIENT_WARMUP` distinct from `INSUFFICIENT_DATA` — "not enough bars for EMA50" is a
  different, *expected* condition for newly listed names and shouldn't read as an error.

### B6. Navigation: "Discover / Trade Ideas / Trade Workspace" replaces my current 5-page nav

You're redefining the top level, so my current `Scanner | Trade Workspace | Context | Reports |
Settings` needs restructuring. My proposal, which preserves everything already built:

- **Discover** = today's Scanner + sector rankings, with the Sector/Industry Explorer as a
  drill-down route (retaining filters + Back), plus the Context strip folded in (levels/GEX are
  decision context, and a separate top-level page is where they get ignored).
- **Trade Ideas** = the aggregate view (new).
- **Trade Workspace** = unchanged.
- **Reports** and **Settings** demoted to secondary (not deleted) — they're operational, not
  part of the discover→trade loop.

I'd rather **fold Context into Discover** than keep it as a fourth primary page, because your
three-page model is about the trading loop and Context is an input to it.

### B7. Chart grid: I would not build it in phase 1

Your brief asks for an optional chart grid, and you explicitly said not to deliver a grid full of
placeholder labels. Given that:
- the grid's value depends on alignment/RS labels being *correct first*;
- it's the most expensive item (lazy loading, per-instrument scales, synchronized time nav);
- and your "build the first complete path" instruction puts the sector→stock→plan→workspace
  path ahead of it —

I propose the grid as **phase 4**, after the path works with real data. Table mode is faster to
get right and is your stated default anyway.

---

## Part C — Refined implementation plan

Phases 1–3 deliver your required first complete path. Nothing ships with placeholder labels.

### Phase 1 — Rules + data contracts (no UI)
- `src/qx/explorer/momo_trend.py`: `MOMO_TREND_RULE_VERSION = "qx_momo_trend_v1"`, EMA20/50,
  slope lookback, ROC(5)+ROC-lookback, neutral band, confirmation persistence, warmup rejection.
  Reuses `scanner.studies.ema`. Emits per-bar states only on **completed** bars, with a separate
  `forming_preview` field.
- Data contracts: `ExplorerUniverse`, `ExplorerRow`, `BreadthBlock`, `AlignmentTrack`
  (`bars_since_alignment`, `previous_state`, `newly_aligned`, `lost_alignment`,
  `feature_values`, `rule_version`).
- **Fixture tests (your requirement 9):** UP/UP, UP/DOWN, DOWN/UP, DOWN/DOWN, and
  missing-history ⇒ `UNKNOWN`. Reproducibility test on completed bars.

### Phase 2 — Explorer service + API
- `src/qx/explorer/service.py`: universe resolution (A vs B, provenance surfaced), dedupe by
  **instrument identity** (CUSIP/FIGI where available; normalized symbol + share-class alias
  handling otherwise — `membership.py` already normalizes `.`→`-` and rejects conflicting
  aliases), ADR/foreign inclusion (do **not** filter to domestic common stock), breadth blocks,
  RS vs parent ETF and vs market on synchronized horizons.
- Routes: `/api/explorer/sectors`, `/api/explorer/sector/{symbol}`,
  `/api/explorer/ideas`, `/api/explorer/notes`.
- Caching so clicking a row does not refetch the universe.

### Phase 3 — Discover UI (Explorer) + AI notes + the complete path
- Discover page: market-context strip, sector/industry selector (11 sectors + industry ETFs like
  SMH), stock table with your exact columns and default `Momentum=UP AND Trend=UP`, the seven
  named views with before/after filter counts, selected-stock detail panel, collapsible AI notes.
- Notes generated **only** from stored evidence, with timestamps, missing inputs, note version,
  and staleness invalidation (reusing the `qx.notes` engine I already built and tested).
- **Demonstrate:** sector selection → aligned stock → qualified playbook → evidence plan →
  prefilled Trade Workspace carrying the same setup identity.

### Phase 4 — Trade Ideas page
- Views: Ready now / Near trigger / Pullback watch / Newly aligned / Bearish — as **views of one
  shared candidate record set**, not parallel scanners.
- "Why ranked here?" (deterministic evidence), Compare (same horizon only), Watch, Open Trade
  Workspace. `UNDERLYING_ONLY` when option data is unavailable.
- Intraday / swing / SPX 1–2DTE profiles strictly separated (daily swing rules must not be
  applied to SPX 1DTE).
- Change tracking vs previous scan; no daily quota — `NOTHING_QUALIFIES` is a valid, visible result.

### Phase 5 — Chart grid (optional, only if 1–4 are verified)
Pinned parent ETF + selected members, common timeframe, **independent price scales**, time-nav
synchronization without copying price levels, lazy-loaded and capped simultaneously.

---

## Part D — Verification plan (and what I will not claim)

Every item in your requirement 9 is covered by a named test. Two I want to flag now:

- **"Retry/reconnect does not duplicate alerts"** — dedupe key is
  `(instrument, timeframe, rule_version, transition)`, and I'll test a reconnect replay
  explicitly. An alignment alert is **never** an order; I'll assert no order path is reachable.
- **"Charts do not share instrument-specific price levels"** — asserted by checking that each
  series is scaled from its own min/max, not the parent's.

**What I will not claim:** parity with your screenshot's Momo/Trend labels (study not present);
complete ETF holdings (top-10 only); SMH constituents (no verified source wired yet). Those will
render as `UNKNOWN` / `MEMBERSHIP_UNAVAILABLE` / `TOP_10_ONLY` until a real source exists.

---

## Part E — Decisions I need from you

1. **Momo/Trend source** — can you export the ThinkScript behind those two labels? If yes I'll
   port and parity-test it; if no, I'll ship `qx_momo_trend_v1` labelled as a baseline.
2. **Industry membership source** — for SMH etc., may I add a provider (e.g. stockanalysis
   holdings HTML, already parseable by `universe.py`) and cache it with provenance, accepting it
   as *unverified* classified membership? Or do you have a preferred constituent source?
3. **Nav restructure** — OK to replace the 5-item nav with Discover / Trade Ideas / Trade
   Workspace, demoting Reports and Settings to secondary, and folding Context into Discover?
4. **Phase order** — confirm the grid belongs in phase 5 (after the path is proven), or tell me
   if you want it earlier and I'll re-sequence.
5. **Confirmation default** — I'll ship `confirmation_bars = 2` but *measure* 1/2/3 and report
   the flip-vs-lag trade-off. Confirm that's the evidence you want.
