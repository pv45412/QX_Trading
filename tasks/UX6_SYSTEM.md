# Task Contract: UX6 System Consolidation

- **task_id:** UX6
- **title:** System Consolidation
- **current state:** COMPLETE

## Goal

Consolidate operational status, provider health, credentials status, jobs, run history, cache/data diagnostics, and configuration visibility into one truthful read-only System destination.

## Dependencies

- UX5 Research is COMPLETE.
- The approved primary navigation and front-half baseline remain locked.

## In scope

- One System workspace with clear operational subviews.
- Reuse existing health, Schwab, cache, jobs, and run-history APIs/components where safe.
- Preserve secret redaction and local-only credential controls.
- Keep legacy System routes as compatibility aliases.
- Responsive desktop, laptop, tablet, and mobile behavior.

## Out of scope

- Trading, lifecycle, threshold, Market Driver, or execution changes.
- New provider/vendor, security, authentication, or credential architecture.
- Legacy deletion, Journal persistence, and broker writes.

## Acceptance criteria

- System is the preferred operational destination with no duplicate source of truth.
- Credentials, tokens, account numbers, and secrets never render or enter logs/tests/screenshots.
- Health and freshness states distinguish healthy, degraded, unavailable, and stale.
- Today, Opportunities, Trade, Portfolio, and Research baseline tests remain green.
- Legacy routes remain reachable and clearly labeled.

## Required tests

- Focused frontend model/component tests and System Playwright coverage.
- Existing Schwab status/health and System API tests.
- UX1 through UX5 compatibility suites.
- Frontend production build, relevant backend regression, and preflight.

## Required checker roles

- Architecture Checker
- Data/Security Semantics Checker
- QA Gatekeeper
- UI/Performance Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

Security/auth architecture changes, new vendors, credential-store changes, destructive migration, or any trading/execution behavior require explicit human approval.

## Rollback / compatibility requirements

Keep existing routes and APIs intact; use additive routing and reversible UI composition. Rollback must restore prior System entry points without affecting canonical workspaces.

## Final deliverables

- Consolidated System workspace and route mapping
- Security/redaction review
- Responsive screenshots
- Test/build/preflight evidence
- Checker verdicts and unresolved-dependency report

## Verification evidence

- All required checker roles returned PASS after one automatic repair cycle.
- Validation and artifact inventory: `data/reports/ux6/validation_results.md`.
- Human/product approval was accepted; UX6 is COMPLETE and all validation evidence remains preserved.

## UI preview requirement

Future visible UX6 repairs must follow `tasks/UI_PREVIEW_LOOP.md`. The completed UX6 evidence predates this policy and remains recorded in `data/reports/ux6/`.
