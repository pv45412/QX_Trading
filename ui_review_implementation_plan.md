# QX Current-State UI Review Package Plan

## Goal

Document the current React QX user experience without redesigning pages, changing
trading behavior, enabling execution, or exposing sensitive brokerage data.

## Scope

- Inventory every canonical workspace route, route alias, side-navigation entry,
  quick-jump destination, major component, and information owner.
- Capture current loaded states at desktop and representative responsive viewports.
- Capture all eight deterministic canonical lifecycle preview states, collapsed and
  with WHY expanded, clearly labeled as fixture data.
- Exercise three read-only user journeys and preserve Playwright screenshots,
  snapshots, traces, and videos.
- Package the documentation and visual evidence under `data/reports/ui_review/`.

## Implementation Boundaries

- Add only review documentation and a Playwright review harness.
- Use the existing loopback React application (`127.0.0.1:5174`) and FastAPI API
  (`127.0.0.1:8510`).
- Do not submit refresh, scan, AI review, credential, OAuth, trade, or broker-write
  actions.
- Mask credential/account fields in the browser before capturing and reject artifacts
  containing known sensitive field patterns.
- Treat missing workflow links or unavailable evidence as factual broken-journey
  findings rather than inventing UI behavior.

## Validation

- Run the complete frontend unit suite.
- Run the production frontend build.
- Run the Playwright UI-review harness with trace and video recording.
- Verify expected artifact counts, ZIP contents, and absence of common secret/token
  patterns before delivery.

## Risks

- Some routes render shared components rather than route-specific workflows; capture
  them separately and record the duplication.
- Live/local data availability can produce empty or degraded states; record the state
  shown without manufacturing data.
- Browser video codecs and trace creation depend on the installed Playwright Chromium
  runtime; report an environment block rather than modifying application behavior.
