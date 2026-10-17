# Market Driver Presentation Contract

## Scope

This document defines a UI-facing contract for a future deterministic market-driver
engine. It does not define driver rules, thresholds, weights, or implementation. The
frontend must not infer a driver from regime, direction, news, volatility, or price.

## User Questions

- What is primarily moving the market or symbol?
- What secondary forces matter?
- Is the driver strengthening, stable, weakening, or unavailable?
- What evidence confirms or conflicts with it?
- Is coverage sufficient to display the conclusion?

## Proposed Read-Only Contract

```json
{
  "status": "AVAILABLE | PARTIAL | UNAVAILABLE | BLOCKED",
  "primary_driver": {
    "driver_id": "stable-backend-id",
    "label": "Broad risk-off / index selling",
    "direction": "BULLISH | BEARISH | MIXED | NEUTRAL",
    "strength": "WEAK | MODERATE | STRONG",
    "persistence": {
      "state": "STRENGTHENING | STABLE | WEAKENING | NEW | UNAVAILABLE",
      "duration_seconds": 2100,
      "started_at": "ISO-8601 timestamp or null"
    }
  },
  "secondary_drivers": [
    {
      "driver_id": "stable-backend-id",
      "label": "Technology-sector weakness",
      "direction": "BEARISH",
      "strength": "MODERATE"
    }
  ],
  "confirming_evidence": [
    {
      "evidence_id": "stable-backend-id",
      "label": "Bearish structure",
      "source_stage": "STRUCTURE",
      "event_timestamp": "ISO-8601 timestamp or null"
    }
  ],
  "conflicting_evidence": [],
  "coverage": {
    "status": "COMPLETE | PARTIAL | INSUFFICIENT | UNAVAILABLE",
    "observed_sources": 4,
    "required_sources": 5,
    "missing_sources": ["gamma"]
  },
  "data_as_of": "ISO-8601 timestamp",
  "knowledge_timestamp": "ISO-8601 timestamp",
  "source": "future deterministic engine",
  "reason_codes": []
}
```

Enums are presentation vocabulary only. Their future calculation requires separate
research and approval.

## Display Hierarchy

### Compact form

Used on Today and Opportunities:

```text
PRIMARY DRIVER      Broad risk-off / index selling
STRENGTH            Strong
PERSISTENCE         Strengthening 35m
EVIDENCE            3 confirming / 1 conflicting
COVERAGE            Partial
```

### Expanded form

Used in Trade Workspace and Research:

```text
Primary
  Broad risk-off / index selling      Strong      Strengthening 35m

Secondary
  Technology-sector weakness          Moderate
  Volatility expansion                Moderate

Confirming
  Bearish structure | Negative delta | Tech weakness | Volatility expansion

Conflicting
  Positive gamma

Coverage
  PARTIAL - gamma source delayed - data as of <timestamp>
```

## Availability Rules

- `AVAILABLE`: show the supplied driver and evidence.
- `PARTIAL`: show the supplied driver with a prominent partial-coverage label.
- `INSUFFICIENT` coverage: do not convert weak evidence into a confident driver.
- `UNAVAILABLE`: show `Market driver unavailable`; retain other canonical stages.
- `BLOCKED`: show the backend reason and link to data health when appropriate.
- Stale timestamps must remain visible and must not be silently refreshed by client
  interpolation.

## Evidence Semantics

- Confirming and conflicting evidence are separate collections.
- Evidence retains source stage, event timestamp, and knowledge timestamp when supplied.
- The primary UI uses readable labels; stable IDs and raw provenance live in audit.
- The frontend may group or order supplied evidence for display, but may not score it,
  recalculate strength, choose the primary driver, or infer persistence.

## Relationship to Canonical Lifecycle

Market Driver is explanatory context, not a new lifecycle gate unless a future approved
engine and pipeline contract explicitly make it one. It cannot promote `WATCH` to
`ARMED`, change direction, or override portfolio risk.

## Security and Telemetry

- Do not include credentials, tokens, raw account identifiers, or order information.
- Telemetry may record driver IDs, status, coverage, timestamps, and render latency.
- Any future engine version must be displayed in audit/provenance.

## Open Contract Questions

1. Is a driver scoped to the broad market, symbol, sector, or all three?
2. What approved service will own driver history and persistence calculations?
3. Which evidence sources are mandatory before coverage can be `COMPLETE`?
4. Should driver changes be stored as canonical transition records?

These require later architecture and quant review; the UI must not answer them.
