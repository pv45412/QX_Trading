# Signal-to-Execution Handoff Design

## Scope Boundary

This is a future UX and data-contract design only. It does not implement Phase 11,
create an order ticket, submit an order, enable paper trading, request broker write
permissions, or change Phase 3-10 behavior.

## Lifecycle Extension

The approved canonical lifecycle remains unchanged through portfolio approval:

```text
WATCH
  -> ARMED
  -> TRIGGERED
  -> TRADEABLE
  -> OPTIONS_SUITABLE
  -> PORTFOLIO_APPROVED
  -> EXECUTION_READY (future, separately approved)
```

`EXECUTION_READY` is not implied by `PORTFOLIO_APPROVED`. It requires a separate,
fresh, deterministic readiness assessment.

## Conceptual Readiness Requirements

All required gates must be positively verified:

1. canonical evaluation is current and publication-eligible
2. required market, quote, and option data is fresh
3. trigger remains valid and has not expired or invalidated
4. tradeability remains passed
5. option expression is still suitable when options are used
6. portfolio risk remains approved
7. requested quantity is within the approved cap
8. spread/slippage constraints are acceptable
9. market/session is eligible
10. duplicate-order/idempotency check passes
11. kill switches and broker/provider health are healthy
12. user/account authorization permits the future action

An unavailable check is not a pass.

## Proposed Future Readiness Contract

```json
{
  "status": "NOT_EVALUATED | CHECKING | EXECUTION_READY | BLOCKED | EXPIRED",
  "evaluation_id": "canonical-evaluation-id",
  "pipeline_version": "core_v1",
  "assessed_at": "ISO-8601 timestamp",
  "valid_until": "ISO-8601 timestamp or null",
  "instrument": "underlying or option contract identifier",
  "side": "future approved intent",
  "quantity_cap": 0,
  "checks": [
    {
      "check_id": "fresh_quote",
      "status": "PASS | FAIL | UNAVAILABLE",
      "data_as_of": "ISO-8601 timestamp or null",
      "reason_code": "stable reason code"
    }
  ],
  "blocking_reason_codes": [],
  "source": "future execution-readiness service"
}
```

This contract is illustrative. Broker/API architecture, idempotency, and authorization
need explicit human approval before implementation.

## Trade Workspace Presentation

Before implementation, show no readiness card or show a clearly disabled placeholder:

```text
FUTURE EXECUTION READINESS
Not evaluated - Phase 11 is not enabled.
Portfolio approval is not an order.
```

After separate approval, the section may show:

- readiness status and expiration
- verified instrument and quantity cap
- freshness countdown based on backend timestamps
- failed/unavailable checks
- kill-switch and duplicate-prevention status
- explicit user confirmation boundary

The frontend must not calculate readiness or turn green based only on lifecycle state.

## Failure and Expiration Semantics

- Any hard-gate failure produces `BLOCKED`.
- Any required unavailable input produces `BLOCKED` or `NOT_EVALUATED`, not ready.
- If canonical trigger/evaluation validity expires, readiness becomes `EXPIRED`.
- A new evaluation or account/quote snapshot invalidates stale readiness as defined by
  the future backend contract.
- A failed readiness check does not rewrite the historical canonical lifecycle result.

## Security and Audit Requirements

Future implementation requires:

- broker write permission approved separately from read-only access
- no tokens, credentials, or raw account numbers in UI/telemetry
- idempotency key and duplicate prevention
- immutable audit linkage among evaluation, readiness assessment, user confirmation,
  and broker response
- kill switches independent of the browser
- server-side quantity and price validation
- explicit environment labeling for any paper/sandbox mode

## Human-Approval Gates

Stop for human approval before deciding:

- broker/vendor and write-access model
- order types and supported asset classes
- slippage/spread thresholds
- readiness expiration windows
- user confirmation and approval roles
- retry/cancel/replace semantics
- kill-switch ownership

None of these decisions are made by this design package.
