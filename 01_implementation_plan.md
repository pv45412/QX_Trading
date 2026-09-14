# Implementation Plan: QX Truth Contract Consolidation & Execution Gating

Consolidate publication metadata contracts across the QX Platform, enforce centralized order execution gating, separate underlying equity price from option contract provenance in the UI, purge/label frontend demo prices, migrate remaining SQLite write paths to the WAL connection helper, and regenerate project walkthrough documentation.

## User Review Required

> [!IMPORTANT]
> **Zero New Trading Features**: This work strictly consolidates financial truth, execution eligibility, frontend metadata, and database connection safety.
> **Order Routing Rejection**: Any order proposal submitted with `publication_state != "VERIFIED"` or `executable = False` will now be explicitly rejected by `OrderRouter` with `OrderStatus.REJECTED`.

## Proposed Changes

---

### Truth Contract & Execution Control

#### [MODIFY] [publication.py](file:///c:/Project/2026/src/qx/models/publication.py)
- Extend `PublicationMetadata` with `to_dict()` and `from_dict()` serialization helpers for unified API responses.

#### [MODIFY] [order_router.py](file:///c:/Project/2026/src/qx/execution/order_router.py)
- Enforce execution eligibility rule in `submit_order()`: reject non-`VERIFIED` or non-`executable` trade requests with `OrderStatus.REJECTED` and explicit error reason.

#### [MODIFY] [web.py](file:///c:/Project/2026/src/qx/interfaces/web.py)
- Integrate `PublicationMetadata` across endpoints emitting signals, analytics, and trade candidates.

---

### Frontend Data Provenance & Demo Price Purge

#### [MODIFY] [QXOptionsIdeas.jsx](file:///c:/Project/2026/web/src/QXOptionsIdeas.jsx)
- Separate underlying equity price provenance (`Verified Schwab Bar Engine`) from option contract & Greeks provenance (`SIMULATED / Modeled Research Prompt`).

#### [MODIFY] [QXDailyNewsPrompt.jsx](file:///c:/Project/2026/web/src/QXDailyNewsPrompt.jsx)
#### [MODIFY] [QXTradingSuite.jsx](file:///c:/Project/2026/web/src/QXTradingSuite.jsx)
#### [MODIFY] [QXInstitutionalScanner.jsx](file:///c:/Project/2026/web/src/QXInstitutionalScanner.jsx)
#### [MODIFY] [QXDayTraderTerminal.jsx](file:///c:/Project/2026/web/src/QXDayTraderTerminal.jsx)
- Remove silent hardcoded fallback prices (`218.29`, `332.27`, `448.20`, `365.44`, `516.13`) or visibly label missing quotes (`[DEMO FALLBACK]` / `N/A (Quote Unavailable)`).

---

### Database Infrastructure

#### [MODIFY] [sector_rotation.py](file:///c:/Project/2026/src/qx/storage/sector_rotation.py)
#### [MODIFY] [workflow.py](file:///c:/Project/2026/src/qx/storage/workflow.py)
#### [MODIFY] [watchlist.py](file:///c:/Project/2026/src/qx/storage/watchlist.py)
#### [MODIFY] [options_flow.py](file:///c:/Project/2026/src/qx/storage/options_flow.py)
#### [MODIFY] [options.py](file:///c:/Project/2026/src/qx/storage/options.py)
#### [MODIFY] [feature_cache.py](file:///c:/Project/2026/src/qx/storage/feature_cache.py)
#### [MODIFY] [command_center.py](file:///c:/Project/2026/src/qx/storage/command_center.py)
- Migrate direct `sqlite3.connect` calls to centralized `connect_sqlite()` WAL helper from `qx.storage.connection`.

---

### Tests & Documentation

#### [MODIFY] [test_phase2_hardening.py](file:///c:/Project/2026/tests/unit/test_phase2_hardening.py)
- Add test verifying that `OrderRouter` rejects non-VERIFIED order proposals.

#### [MODIFY] [02_walkthrough.md](file:///c:/Project/2026/02_walkthrough.md)
- Update walkthrough with exact environment details, dependency-install command, commit SHA, pytest command, and test counts (9 tests in Phase 2 suite, 1691 full suite).

## Verification Plan

### Automated Tests
- `.\.venv\Scripts\python.exe -m pytest tests/unit/test_phase2_hardening.py -v`
- `rg "218\.29|332\.27|448\.20|365\.44|516\.13" web/src/`

### Manual Verification
- Verify React UI components load and display proper provenance separation and demo fallback labels.
