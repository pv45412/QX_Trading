# BE2 Validation Plan: Historical Replay, Fixtures & Anti-Leakage Verification

## 1. Objectives

The BE2 validation suite must deterministically prove:
1. **Zero Future Lookahead**: No price, pivot, or indicator data beyond $T_{\text{eval}}$ can influence an evaluation.
2. **Timeframe Isolation**: Modifying, delaying, or corrupting HTF data cannot corrupt the primary timeframe's bar index, timestamp alignment, or local calculations.
3. **Candle Knowledge Timing**: HTF candles are ingested at their exact completion/knowledge timestamp boundary.
4. **Deterministic Reproducibility**: Replaying the same multi-timeframe bar set produces byte-for-byte identical evaluation results and SHA256 hashes.

---

## 2. Validation Test Suite Architecture

We propose four dedicated test modules to be created during BE2 implementation:

### Suite A: Causality & Lookahead Prevention (`tests/unit/test_be2_causality.py`)
- **Test 1: Mid-Candle Incomplete Bar Shielding**:
  - Setup: Primary TF = 5m, HTF = 1h. Evaluation timestamp $T_{\text{eval}} = \text{10:35:00 UTC}$.
  - Test: Inject a 1h bar spanning 10:00 to 11:00 with an extreme high at 10:55.
  - Verification: At 10:35:00, the HTF structure analyzer must only see the 1h bar that closed at 10:00:00. The incomplete 10:00–11:00 bar must be completely omitted from HTF SMC calculations.
- **Test 2: Post-Cutoff Mutation Invariance**:
  - Setup: Evaluate symbol at $T_0$. Mutate bars occurring at $T > T_0$.
  - Verification: $\text{SHA256}(\text{Result}(T_0))_{\text{before}} == \text{SHA256}(\text{Result}(T_0))_{\text{after}}$.
- **Test 3: Candle Close Boundary Precision**:
  - For an HTF bar closing at exactly 10:00:00:
    - At 09:59:59.999: HTF bar is invisible (status `INCOMPLETE` or omitted).
    - At 10:00:00.000: HTF bar becomes visible.

### Suite B: Timeframe Alignment & Missing Data Resilience (`tests/unit/test_be2_timeframe_alignment.py`)
- **Test 1: Missing HTF Stream**:
  - Pass valid 5m bars but an empty HTF bar set.
  - Verify:
    - Under Option A: Emits `BLOCKED` with reason code `HTF_DATA_MISSING`.
    - Under Option B: Emits `ARMED` with coverage `0.90` and Factor #7 marked `UNAVAILABLE`.
    - No unhandled exceptions or NaN propagations.
- **Test 2: Stale HTF Stream**:
  - Pass HTF bars that are 50 bars older than $T_{\text{eval}}$.
  - Verify HTF Factor receives `reliability_multiplier = 0.50` and freshness status `STALE`.
- **Test 3: Non-Standard Market Hours & Calendar Shifting**:
  - Half-day sessions (13:00 close), market holidays, and DST transition weekends.
  - Verify that daily bars do not aggregate into future closed bars on abbreviated trading days.

### Suite C: Replay vs. Live Stream Parity (`tests/unit/test_be2_replay_parity.py`)
- **Test 1: Step-by-Step Replay vs. Batch Pipeline**:
  - Step `HistoricalReplayAdapter` through 200 bars across synchronized 5m and 1h data.
  - Compare the output against single-point evaluations at each step.
  - Verify identical `LifecycleState`, `direction_score`, `reason_codes`, and `evaluated_bar_window_sha256`.

### Suite D: Multi-Timeframe Opportunity Persistence (`tests/unit/test_be2_persistence_parity.py`)
- **Test 1: Multi-Timeframe Opportunity Serialization**:
  - Verify `OpportunityRecord` and `OpportunityListItem` correctly serialize and deserialize `timeframe`, `horizon_context`, and multi-timeframe data dependency hashes.
- **Test 2: Deduplication & Stream Key Integrity**:
  - Confirm stream keys maintain uniqueness across distinct horizons and timeframes without colliding.

---

## 3. Synthetic & Real-World Fixtures

1. **`fixtures/mtf_spy_synchronized_sample.json`**:
   - Synchronized 1m, 5m, 15m, 1h, and Daily bars for SPY covering a full FOMC trading session.
   - Contains explicit start and end timestamps for every candle.
2. **`fixtures/mtf_lookahead_adversarial.json`**:
   - Craftily structured bars containing subtle future price leaks in higher timeframe aggregates to trap naive filters.
