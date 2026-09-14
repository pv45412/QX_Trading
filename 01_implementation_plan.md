# P0 Financial Integrity & Architecture Remediation Plan

Close the remaining P0 financial-integrity issues and architectural decoupling items identified in the platform review.

## User Review Required

> [!IMPORTANT]
> - **Truth Control**: Options Scanner ideas with modeled/simulated options flow will explicitly emit `publication_state = SIMULATED` and `executable = False` until backed by verified live chains.
> - **Stale Price Removal**: Hard-coded price fallbacks (e.g. `218.29`) are eliminated. Unavailable market quotes produce `publication_state = BLOCKED` / `None`.
> - **Put Credit Spread Math**: Constructing a put credit spread without a valid lower-strike long put returns `None` (full stop). Invention of fallback spread widths is deleted.
> - **Payoff Topology**: `generate_strategy_payoff` will pass `legs` into `calculate_risk_reward(pnls, legs=legs)` so analytical tail risk (unlimited upside/downside) is evaluated mathematically rather than bounded by grid sampling windows.
> - **Decoupled Basis Math**: Pure arithmetic for `/ES` to `SPX` basis will be moved to a zero-dependency module `price_normalization.py`, eliminating yfinance/broker import failures during unit tests.

## Proposed Changes

---

### Core Data & Truth Gating

#### [NEW] [price_normalization.py](file:///c:/Project/2026/src/qx/market/price_normalization.py)
- Pure math functions with zero external/provider dependencies:
  - `calculate_es_spx_basis(es_price: float, spx_price: float) -> dict[str, Any]`
  - `es_to_spx(es_target: float, basis: float) -> float`

#### [MODIFY] [order_router.py](file:///c:/Project/2026/src/qx/execution/order_router.py)
- Consume `price_normalization.py` for basis math.
- Add `get_batch_basis_snapshot(market_data_provider)` to retrieve `/ES` and `$SPX` quotes together and preserve quote timestamps.

#### [MODIFY] [ticker_service.py](file:///c:/Project/2026/src/qx/market/ticker_service.py)
- Remove hardcoded default price substitutions (`218.29`, etc.) when fetching quotes; return `price = None` / explicit unavailable state when market bars are unavailable.

---

### Options Scanner & Strategy Trade Construction

#### [MODIFY] [trade_constructor.py](file:///c:/Project/2026/src/qx/options_scanner/services/trade_constructor.py)
- Enforce strict 2-leg spread validation for Put Credit Spreads:
  - If `long_puts` is empty or no valid lower-strike, same-expiration long put is found, return `None`.
  - Remove `long_put = short_put` fallback and remove `width = round(...) or 5.0` width invention.

#### [MODIFY] [web.py](file:///c:/Project/2026/src/qx/interfaces/web.py)
- Ensure `/api/options-scanner/ideas` returns `publication_state = SIMULATED` and `executable = False` whenever option contracts are modeled or simulated.

---

### Payoff Engine & Risk Topology

#### [MODIFY] [payoff/__init__.py](file:///c:/Project/2026/src/qx/strategies/payoff/__init__.py)
- Pass `legs` to `calculate_risk_reward(pnls, legs=legs)` inside `generate_strategy_payoff()`, connecting analytical unlimited tail risk classification to the main payoff evaluation path.

---

### Options Analytics & Settlement Provenance

#### [MODIFY] [gex.py](file:///c:/Project/2026/src/qx/options/gex.py)
- Add structured settlement provenance tracking:
  - `settlement_source`: `EXPLICIT_PROVIDER`, `SERIES_ROOT`, `EXPIRATION_METADATA`, `HEURISTIC_DTE`, `UNKNOWN`
  - `settlement_confidence`: `VERIFIED`, `HIGH`, `HEURISTIC`, `UNVERIFIED`
- Tag `dte == 0` fallbacks as `HEURISTIC` confidence rather than assuming verified PM settlement.

---

### Test Suite & Verification

#### [MODIFY] [test_phase2_hardening.py](file:///c:/Project/2026/tests/unit/test_phase2_hardening.py)
- Add unit tests for `price_normalization.py`, Put Credit Spread `None` return on missing long put, payoff topology `legs` analytical risk calculation, and GEX settlement provenance.

---

## Verification Plan

### Automated Tests
- Full pytest suite: `.\.venv\Scripts\python.exe -m pytest tests/`
- React test suite: `npm test -- --run` in `web/`
- System preflight checks: `.\.venv\Scripts\python.exe -m qx.tools.run_preflight_checks`

### Manual Verification
- Verify 100% pass across all unit tests without yfinance or provider import errors.
- Regenerate `walkthrough.md` with actual test count and results.
