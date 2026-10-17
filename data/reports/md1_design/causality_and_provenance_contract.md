# MD1 Causality, Provenance, and Fail-Closed Contract

**Task**: MD1 Market Driver Engine Design  
**Authoritative Role**: Data Semantics & Causality Specialist  
**Status**: DESIGN ARTIFACT (Read-Only Investigation)  

---

## 1. Core Causality & Point-in-Time Invariant

The Market Driver Engine evaluates explanatory forces strictly at evaluation timestamp $T_{\text{eval}}$.

### Strict Point-in-Time Rule
For any observed evidence, metric, or source snapshot $S$:
$$T_{\text{source\_event}}(S) \le T_{\text{knowledge}}(S) \le T_{\text{eval}}$$

Under no circumstances may any component of the Market Driver Engine inspect:
1. Candle closes occurring after $T_{\text{eval}}$ ($T_{\text{bar\_close}} > T_{\text{eval}}$).
2. Index or sector metrics derived from future intervals.
3. Order flow or delta aggregations computed over unclosed future windows.
4. Macroeconomic news releases or event flags before their official publication timestamp.

---

## 2. Dependency Taxonomy & Freshness SLAs

The engine monitors five distinct evidence families:

| Evidence Family | Feed / Source | Mandatory? | Max Freshness SLA | Stale Penalty Multiplier |
| :--- | :--- | :--- | :--- | :--- |
| **`underlying`** | Primary symbol OHLCV & quote | **Yes** | 30 seconds | Fails closed to `BLOCKED` if missing |
| **`index`** | SPY / QQQ benchmark bars & alignment | **Yes** | 60 seconds | Reliability $\times 0.50$ |
| **`sector`** | Sector ETF relative strength | Recommended | 120 seconds | Reliability $\times 0.50$ |
| **`delta`** | Order flow / aggressor delta | Recommended | 60 seconds | Reliability $\times 0.50$ |
| **`gamma`** | GEX / dealer gamma snapshot | Optional | 900 seconds (15m) | Reliability $\times 0.50$ |

---

## 3. Deterministic Coverage Calculation

The engine calculates coverage status based on the count and quality of available evidence families:

```python
TOTAL_REQUIRED_SOURCES = 5  # underlying, index, sector, delta, gamma

observed_count = sum(1 for source in sources if source.available and source.freshness != "STALE_EXPIRED")
```

### Coverage State Hierarchy:
1. **`COMPLETE`**:
   - `observed_count == 5`
   - All sources fresh and synchronized.
   - Confidence multiplier = 1.0.
2. **`PARTIAL`**:
   - `observed_count` is 3 or 4 (e.g., gamma delayed or sector feed unavailable).
   - The primary driver may be published, but the UI must display a prominent `PARTIAL` badge with explicit `missing_sources`.
   - Confidence multiplier = $\frac{\text{observed\_count}}{5.0}$.
3. **`INSUFFICIENT`**:
   - `observed_count < 3` OR benchmark index feed is completely missing.
   - **Fail-Closed Rule**: The engine must NOT invent or extrapolate a driver from thin air.
   - Emits `status = "INSUFFICIENT"` or `"UNAVAILABLE"`, `primary_driver = None`, and reason code `INSUFFICIENT_EVIDENCE_COVERAGE`.
4. **`BLOCKED`**:
   - Upstream data corruption, temporal inversion ($T_{\text{data}} > T_{\text{eval}}$), or missing underlying bars.

---

## 4. Reason Code Catalog

To maintain end-to-end traceability and auditability, all decisions emit standardized reason codes:

| Reason Code | Meaning | Outcome Status |
| :--- | :--- | :--- |
| `DRIVER_AVAILABLE_COMPLETE` | All 5 evidence families present and fresh; driver verified. | `AVAILABLE` |
| `DRIVER_AVAILABLE_PARTIAL` | Driver verified with 3 or 4 evidence families; non-critical source missing. | `PARTIAL` |
| `INSUFFICIENT_EVIDENCE_COVERAGE` | Fewer than 3 evidence families available; cannot reliably attribute driver. | `UNAVAILABLE` |
| `INDEX_BENCHMARK_UNAVAILABLE` | Benchmark index feed missing; cannot determine systemic vs idiosyncratic flow. | `UNAVAILABLE` |
| `TEMPORAL_INVERSION_DETECTED` | Feed timestamp is in the future relative to evaluation timestamp; pipeline safety trigger. | `BLOCKED` |
| `STALE_DELTA_FEED` | Order flow delta feed exceeded max freshness SLA; reliability degraded. | Informational / `PARTIAL` |
| `GAMMA_SOURCE_DELAYED` | Dealer gamma snapshot is delayed or uncomputed. | Informational / `PARTIAL` |
| `HYSTERESIS_MAINTAINED` | Incumbent primary driver retained because candidate did not exceed hysteresis hurdle. | Informational |

---

## 5. Provenance & Cryptographic Audit

Every evaluated `MarketDriverResult` includes:
- `data_as_of`: Earliest and latest data timestamp across observed feeds.
- `knowledge_timestamp`: The exact wall-clock time the evaluation executed.
- `engine_version`: Semantic engine version (e.g. `market_driver_v1.0.0`).
- `input_fingerprint`: SHA256 hash of the input vector.
- `observed_sources`: List of active source IDs and their individual freshness states.
