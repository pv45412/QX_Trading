# QX Current-State UI Review Package

This package documents the UI as it exists. It contains no redesign, trading-rule
change, execution behavior, credential value, OAuth token, or broker account number.

## Contents

- `page_inventory.md`: all 22 route labels, navigation entries, data sources, actions,
  implementation class, duplication, feature flags, and known gaps.
- `navigation_map.md`: top, left, subroute, quick-jump, alias, and workflow paths.
- `information_matrix.md`: current ownership of key trading and operational evidence.
- `component_inventory.md`: major React components and overlap.
- `current_ux_findings.md`: factual observations separated from product questions.
- `screenshots/desktop/`: routed pages, quick-jump surfaces, and lifecycle previews.
- `screenshots/responsive/`: six important surfaces at desktop, laptop, and mobile.
- `traces/`: Playwright journey traces with screenshots and DOM snapshots.
- `videos/`: WebM recordings of the three read-only journeys.
- `capture_results.json`: machine-readable capture status and broken-journey findings.

## Inspecting Traces

From `web/`, run:

```powershell
npx playwright show-trace ..\data\reports\ui_review\traces\day_trader.zip
npx playwright show-trace ..\data\reports\ui_review\traces\swing_trader.zip
npx playwright show-trace ..\data\reports\ui_review\traces\long_term_investor.zip
```

## Capture Semantics

- Routed and responsive screenshots use the current local React application and saved
  backend data.
- The capture harness uses the latest saved analytics `as_of` where available to avoid
  triggering background provider/cache refresh.
- Browser `fetch` is wrapped before application code runs so every non-GET request is
  answered locally with empty JSON and never reaches the backend. A Playwright route
  guard provides a second fail-closed boundary.
- Schwab credential status is retained except that the client-ID suffix is removed.
- Password/callback inputs are cleared and visually masked before capture.
- Lifecycle screenshots are deterministic fixtures and visibly labeled
  `TEST / PREVIEW DATA — NOT LIVE`.
- Missing links or unavailable evidence are recorded as journey breaks rather than
  replaced with synthetic workflow behavior.

## Scope Boundary

No Phase 11 work, order submission, broker write access, UI redesign, route removal,
or trading-logic change is included.
