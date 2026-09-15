# Code Quality Rule: Defensive Formatting & Contract Safety

## Core Principles

1. **Defensive Numeric Formatting**:
   - Never call `.toFixed()` directly on a raw variable or object property.
   - Always wrap values defensively: `(Number(val) || 0).toFixed(decimals)`.
   - Prevent runtime `TypeError: Cannot read properties of null (reading 'toFixed')` crashes across all UI templates.

2. **ErrorBoundary Component Wrapping**:
   - Every workspace section and major card must be wrapped inside an `<ErrorBoundary title="...">` component.
   - Failures in one sub-widget must never crash the surrounding dashboard.

3. **Fail-Closed API State**:
   - Uninitialized, stale, or unavailable backend data must return explicit `publication_state` (`BLOCKED` or `SIMULATED`) and `executable: False`.
   - Never substitute synthetic equity assumptions (e.g. `$500,000`).

4. **100x Option Multiplier Math**:
   - All option position market values (`quantity * price * 100`) and net portfolio Greeks (`quantity * greek * 100`) must strictly apply the 100x contract multiplier.
