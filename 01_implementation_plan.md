# Phase 2 Hardening Implementation Plan

Remediate the three remaining architecture hardening items across execution, gamma exposure options modeling, and frontend-backend data contracts.

## User Review Required

> [!IMPORTANT]
> - **Execution Layer**: Dynamic basis tracking will compute `live_basis = es_price - spx_price` directly inside order generation routines, overriding static/cached basis values.
> - **GEX Modeling**: SPXW (PM-settled weeklies/0DTE) and SPX (AM-settled monthlies) will be segregated when computing gamma walls to prevent false pinning strike levels.
> - **Data Contracts**: Property key alignment and fallback null-checks will be enforced between Python backend responses and React frontend utilities.

## Proposed Changes

---

### Execution Layer

#### [MODIFY] [order_router.py](file:///c:/Project/2026/src/qx/execution/order_router.py)
- Enhance `OrderRouter` with instantaneous basis tracking:
  - Add `calculate_live_basis(es_price: float, spx_price: float) -> dict[str, Any]` to calculate `live_basis = es_price - spx_price` at the instant of order creation.
  - Add dynamic `es_target_to_spx_strike()` target conversion inside order request processing to ensure strike selection uses live market ticks rather than cached offsets.

---

### Options & Volatility Analytics

#### [MODIFY] [gex.py](file:///c:/Project/2026/src/qx/options/gex.py)
- Update `calculate_gamma_exposure()` to support AM/PM settlement segregation:
  - Detect `settlement_type` or symbol classification (`SPXW` vs `SPX`).
  - Separate PM-settled 0DTE/weekly contracts from AM-settled monthly contracts during strike-level gamma aggregation.
  - Return segregated gamma walls (`top_call_gamma_strike`, `top_put_gamma_strike`, `gamma_flip_price`) to prevent false pinning levels.

---

### Data Contracts & Web Layer

#### [MODIFY] [data_contracts.py](file:///c:/Project/2026/src/qx/market/data_contracts.py)
- Add payload key schemas and validation helpers matching React frontend dashboard properties for `/api/spx-calendars`, `/api/gex-snapshot`, and `/api/news-stream`.

#### [MODIFY] [data-utils.js](file:///c:/Project/2026/web/src/data-utils.js)
- Add safety null-checks, defensive property getters (`safeGet()`, fallback defaults for missing numeric metrics), and payload contract validation helpers.

---

### Test Suite

#### [NEW] [test_phase2_hardening.py](file:///c:/Project/2026/tests/unit/test_phase2_hardening.py)
- Unit tests verifying dynamic basis tracking in `order_router.py`, AM/PM GEX segregation in `gex.py`, and data contract compatibility.

---

## Verification Plan

### Automated Tests
- Full pytest suite: `.\.venv\Scripts\python.exe -m pytest tests/`
- React test suite: `npm test -- --run` in `web/`
- System preflight checks: `.\.venv\Scripts\python.exe -m qx.tools.run_preflight_checks`

### Manual Verification
- Verify preflight output and ensure 100% test pass rate across all 1,640+ repository unit tests.
