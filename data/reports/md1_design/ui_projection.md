# MD1 UI Projection and Presentation Contract

**Task**: MD1 Market Driver Engine Design  
**Authoritative Role**: UX / Product Systems Specialist  
**Status**: DESIGN ARTIFACT (Read-Only Investigation)  

---

## 1. Compliance with Baseline Design Contract

This projection adheres 100% to the product design contract established in `data/reports/qx_product_design/market_driver_spec.md`.

### Cardinal Frontend Rule
> **The frontend must NEVER infer or calculate a Market Driver.**  
> It must act strictly as a passive renderer of the authoritative backend `market_driver` payload. If the backend emits `UNAVAILABLE`, the UI renders "Market driver unavailable". It must not extrapolate from regime, direction, price change, or technical indicators.

---

## 2. API Contract Schema

The backend will emit the following deterministic JSON structure attached to evaluations, opportunity records, and opportunity list items:

```json
{
  "status": "AVAILABLE",
  "primary_driver": {
    "driver_id": "INDEX_RISK_OFF",
    "label": "Broad risk-off / index selling",
    "direction": "BEARISH",
    "strength": "STRONG",
    "persistence": {
      "state": "STRENGTHENING",
      "duration_seconds": 2100,
      "started_at": "2026-09-17T13:45:00Z"
    }
  },
  "secondary_drivers": [
    {
      "driver_id": "SECTOR_LAG",
      "label": "Technology sector weakness",
      "direction": "BEARISH",
      "strength": "MODERATE"
    },
    {
      "driver_id": "GAMMA_SQUEEZE",
      "label": "Negative gamma acceleration",
      "direction": "BEARISH",
      "strength": "MODERATE"
    }
  ],
  "confirming_evidence": [
    {
      "evidence_id": "STRUCTURE_BEARISH_BOS",
      "label": "Bearish structure break (BOS)",
      "source_stage": "STRUCTURE",
      "event_timestamp": "2026-09-17T14:15:00Z"
    },
    {
      "evidence_id": "NEGATIVE_DELTA_EXPANSION",
      "label": "Aggressive seller delta (-74.2)",
      "source_stage": "DELTA",
      "event_timestamp": "2026-09-17T14:18:30Z"
    },
    {
      "evidence_id": "SECTOR_OUTFLOW",
      "label": "XLK relative strength -48.5",
      "source_stage": "SECTOR",
      "event_timestamp": "2026-09-17T14:19:00Z"
    }
  ],
  "conflicting_evidence": [
    {
      "evidence_id": "VWAP_SUPPORT_PROXIMITY",
      "label": "Approaching session VWAP",
      "source_stage": "VWAP",
      "event_timestamp": "2026-09-17T14:19:30Z"
    }
  ],
  "coverage": {
    "status": "PARTIAL",
    "observed_sources": 4,
    "required_sources": 5,
    "missing_sources": ["gamma"]
  },
  "data_as_of": "2026-09-17T14:19:30Z",
  "knowledge_timestamp": "2026-09-17T14:20:00Z",
  "engine_version": "market_driver_v1.0.0",
  "reason_codes": ["DRIVER_AVAILABLE_PARTIAL", "GAMMA_SOURCE_DELAYED"]
}
```

---

## 3. Visual Layout Projections

### A. Compact Form (Today & Opportunities Workspaces)
Rendered within Opportunity cards and tabular summaries:

```text
┌─────────────────────────────────────────────────────────────┐
│ MARKET DRIVER                                               │
│ Broad risk-off / index selling                   [ STRONG ] │
│ ─────────────────────────────────────────────────────────── │
│ Persistence: Strengthening (35m)                            │
│ Evidence:    3 Confirming  •  1 Conflicting                 │
│ Coverage:    PARTIAL (gamma missing)                        │
└─────────────────────────────────────────────────────────────┘
```

### B. Expanded Form (Trade & Research Workspaces)
Rendered as an interactive Bento card adjacent to the Market Regime and Direction panels:

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ MARKET DRIVER ATTRIBUTION                           [ STATUS: AVAILABLE ] │
├───────────────────────────────────────────────────────────────────────────┤
│ PRIMARY DRIVER                                                            │
│ ▼ Broad risk-off / index selling        STRENGTH: Strong   STABLE (42m)   │
│                                                                           │
│ SECONDARY DRIVERS                                                         │
│ • Technology sector weakness            STRENGTH: Moderate                │
│ • Negative gamma acceleration           STRENGTH: Moderate                │
│                                                                           │
│ CONFIRMING EVIDENCE (3)                                                   │
│ [Bearish Structure BOS]  [Seller Delta -74.2]  [XLK Outflow -48.5]        │
│                                                                           │
│ CONFLICTING EVIDENCE (1)                                                  │
│ [Approaching Session VWAP]                                                │
│                                                                           │
│ COVERAGE AUDIT                                                            │
│ COMPLETE (5/5 Sources Verified) • Data as of 14:19:30 UTC                 │
│ Engine: market_driver_v1.0.0 • Latency: 1.8ms                             │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Visual Availability States

| Status | Visual Styling | Badge / Label | Interactive Behavior |
| :--- | :--- | :--- | :--- |
| **`AVAILABLE`** | Border: Accent/Theme; Header: Bright text | Solid green/blue `COMPLETE` badge | Hover reveals evidence breakdown and timestamps. |
| **`PARTIAL`** | Border: Warning Amber; Header: Amber text | Amber `PARTIAL (4/5)` badge | Hover displays explicit `missing_sources` tooltip. |
| **`INSUFFICIENT`**| Border: Neutral Muted; Header: Muted text | Neutral `INSUFFICIENT COVERAGE` | Tooltip explains missing sources; primary driver hidden. |
| **`UNAVAILABLE`** | Border: Dim Gray; Text: `Market driver unavailable` | Gray `UNAVAILABLE` badge | Retains clean layout; explains backend reason code. |
| **`BLOCKED`** | Border: Error Rose; Text: `Driver data blocked` | Rose `DATA ERROR` badge | Operator alerted to data pipeline health issue. |
