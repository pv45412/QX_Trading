# Final P0 Financial Truth Hardening Implementation Plan

Close the remaining financial-truth gating and stale fallback quote issues across endpoints, telemetry, and frontend components.

## User Review Required

> [!IMPORTANT]
> - **Simulated Scanner Gating**: `/api/options-scanner/ideas` will explicitly emit `publication_state = SIMULATED`, `executable = false`, and `evidence_reason = "Option contracts and Greeks are modeled and are not verified from a live option chain."`
> - **Stale Quote Fallback Elimination**: Hard-coded fallback price defaults (`p_nvda = quote_nvda.price or 218.29`, `332.27`, `448.20`, `365.44`, `516.13`) and fallback date strings (`"2026-09-11 Verified Daily Close"`) are completely deleted. Missing quotes will produce `publication_state = BLOCKED`, `executable = false`, and block trade generation.
> - **Telemetry Zero Sample Null**: `TelemetryService.calculate_calibrated_win_rate()` with zero completed outcomes will return `empirical_win_rate_pct = None` (`null` in JSON) instead of defaulting to `55.0`.
> - **UI Research Only Indicator**: `QXOptionsIdeas.jsx` will display a prominent `[SIMULATED / RESEARCH ONLY]` warning banner.

## Proposed Changes

---

### Backend Endpoints & Market Ticker Service

#### [MODIFY] [web.py](file:///c:/Project/2026/src/qx/interfaces/web.py)
- Update `/api/options-scanner/ideas`:
  - Remove all hard-coded price fallbacks (`quote_nvda.price or 218.29`, `332.27`, `448.20`, `365.44`, `516.13`) and fallback date string `"2026-09-11 Verified Daily Close"`.
  - Filter out symbols where market quote price is unavailable (`<= 0`).
  - Emit `publication_state = "SIMULATED"`, `executable = False`, and `evidence_reason = "Option contracts and Greeks are modeled and are not verified from a live option chain."`
  - If all quotes fail, set `publication_state = "BLOCKED"` and return no actionable trade ideas.

#### [MODIFY] [ticker_service.py](file:///c:/Project/2026/src/qx/market/ticker_service.py)
- Delete `REAL_SYMBOL_BASELINES` hard-coded price fallbacks in quote resolution. Unresolved ticker quotes return `price = 0.0` and `as_of = "BLOCKED: Market Quote Unavailable"`.

---

### Telemetry Calibration

#### [MODIFY] [service.py](file:///c:/Project/2026/src/qx/telemetry/service.py)
- In `calculate_calibrated_win_rate()`, when `not filtered` (zero completed outcomes), return `empirical_win_rate_pct = None` (`null` in JSON) and `calibrated = False`.

---

### Frontend React Display

#### [MODIFY] [QXOptionsIdeas.jsx](file:///c:/Project/2026/web/src/QXOptionsIdeas.jsx)
- Render a prominent `[SIMULATED / RESEARCH ONLY]` warning banner indicating option contracts are modeled and live execution is blocked.

---

### Regression Unit Tests & Verification

#### [MODIFY] [test_phase2_hardening.py](file:///c:/Project/2026/tests/unit/test_phase2_hardening.py)
- Add regression unit tests proving:
  1. Options scanner response is `SIMULATED` and `executable = False`.
  2. No hard-coded fallback prices (`218.29`, etc.) are substituted when quotes fail.
  3. Missing/failed quotes result in `publication_state = BLOCKED`.
  4. Zero telemetry observations return `empirical_win_rate_pct = None`.

---

## Verification Plan

### Automated Tests
- Ripgrep audit: `rg "218\.29|332\.27|448\.20|365\.44|516\.13" src/qx/` (must return zero matches).
- Pytest suite: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_phase2_hardening.py`
- Full test suite: `.\.venv\Scripts\python.exe -m pytest -q`
- React test suite: `npm test -- --run` in `web/`

### Manual Verification
- Verify `02_walkthrough.md` is updated after all tests pass with zero failures.
