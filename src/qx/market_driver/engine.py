"""MD2 Market Driver Engine.

Deterministic, point-in-time Market Driver evaluation using continuous multi-factor
decomposition with hysteresis (approved MD1 Option B contract).

Strictly explanatory: ZERO lifecycle authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from qx.config.rules_config import MarketDriverConfig, RulesEngineConfig
from qx.market_driver.models import (
    ARCHETYPE_LABELS,
    CoverageAudit,
    DriverArchetype,
    DriverDirection,
    DriverPersistence,
    DriverStrength,
    EvidenceClassification,
    EvidenceToken,
    MarketDriverResult,
    MarketDriverStatus,
    PersistenceState,
    PrimaryDriver,
    SecondaryDriver,
)


def _aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _classify_strength(magnitude: float, config: MarketDriverConfig) -> DriverStrength:
    thresh = config.thresholds
    if magnitude >= thresh.strong_threshold:
        return DriverStrength.STRONG
    elif magnitude >= thresh.moderate_threshold:
        return DriverStrength.MODERATE
    else:
        return DriverStrength.WEAK


def _fingerprint_inputs(symbol: str, eval_ts: datetime, inputs: Dict[str, Any]) -> str:
    raw = {
        "symbol": symbol.upper(),
        "eval_ts": eval_ts.isoformat(),
        "inputs": inputs,
    }
    dumped = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


class MarketDriverEngine:
    """Continuous Multi-Factor Market Driver Decomposition Engine with Hysteresis."""

    def __init__(self, config: Optional[MarketDriverConfig] = None) -> None:
        self.config = config or MarketDriverConfig()

    def evaluate(
        self,
        ctx: Any,
        previous_result: Optional[MarketDriverResult] = None,
        rules_config: Optional[RulesEngineConfig] = None,
    ) -> MarketDriverResult:
        """Evaluates market drivers deterministically from evaluation context."""
        config = rules_config.market_driver if rules_config else self.config
        eval_time = _aware_utc(ctx.evaluation_timestamp) or datetime.now(timezone.utc)

        reason_codes: List[str] = []

        # ---------------------------------------------------------------------
        # 1. Evidence Coverage Audit (5 Families)
        # ---------------------------------------------------------------------
        source_details: Dict[str, Any] = {}
        missing_sources: List[str] = []

        # Family 1: Underlying (OHLCV & quote) - MANDATORY
        bars = getattr(ctx, "bars", None)
        underlying_available = False
        underlying_freshness = "UNAVAILABLE"
        if bars is not None and isinstance(bars, pd.DataFrame) and not bars.empty:
            underlying_available = True
            underlying_freshness = "FRESH"
        elif bars is not None and hasattr(bars, "__len__") and len(bars) > 0:
            underlying_available = True
            underlying_freshness = "FRESH"

        source_details["underlying"] = {
            "available": underlying_available,
            "freshness": underlying_freshness,
            "provenance": "CANONICAL_BARS",
        }
        if not underlying_available:
            missing_sources.append("underlying")

        # Family 2: Index Benchmark (SPY/QQQ alignment) - MANDATORY
        market_alignment_score = getattr(ctx, "market_alignment_score", None)
        market_alignment_age = getattr(ctx, "market_alignment_age_seconds", 0)
        index_available = market_alignment_score is not None
        index_freshness = "FRESH"
        index_reliability = 1.0

        if index_available:
            if market_alignment_age > config.freshness.index_max_age_seconds:
                index_freshness = "STALE"
                index_reliability *= config.freshness.stale_reliability_multiplier
                reason_codes.append("STALE_INDEX_FEED")
            source_details["index"] = {
                "available": True,
                "freshness": index_freshness,
                "reliability": index_reliability,
                "score": market_alignment_score,
                "provenance": "INDEX_BENCHMARK_ALIGNMENT",
            }
        else:
            source_details["index"] = {"available": False, "freshness": "UNAVAILABLE"}
            missing_sources.append("index")

        # Family 3: Sector Relative Strength
        sector_rs_score = getattr(ctx, "relative_strength_score", None)
        sector_rs_age = getattr(ctx, "sector_rs_age_seconds", 0)
        sector_available = sector_rs_score is not None
        sector_freshness = "FRESH"
        sector_reliability = 1.0

        if sector_available:
            if sector_rs_age > config.freshness.sector_max_age_seconds:
                sector_freshness = "STALE"
                sector_reliability *= config.freshness.stale_reliability_multiplier
                reason_codes.append("STALE_SECTOR_FEED")
            source_details["sector"] = {
                "available": True,
                "freshness": sector_freshness,
                "reliability": sector_reliability,
                "score": sector_rs_score,
                "provenance": "SECTOR_RELATIVE_STRENGTH",
            }
        else:
            source_details["sector"] = {"available": False, "freshness": "UNAVAILABLE"}
            missing_sources.append("sector")

        # Family 4: Microstructure / Order Flow Delta
        delta_val = getattr(ctx, "delta_value", None)
        delta_prov = getattr(ctx, "delta_provenance", "UNAVAILABLE")
        delta_age = getattr(ctx, "delta_age_seconds", 0)
        delta_available = delta_val is not None and str(delta_prov).upper() != "UNAVAILABLE"
        delta_freshness = "FRESH"
        
        # Provenance-aware delta reliability
        prov_str = str(delta_prov).upper()
        if prov_str == "ACTUAL_TRADE_AGGRESSOR":
            delta_reliability = 1.0
        elif prov_str == "ESTIMATED_BID_ASK":
            delta_reliability = 0.75
        elif prov_str == "BAR_DERIVED":
            delta_reliability = 0.40
        else:
            delta_reliability = 0.0

        if delta_available and delta_reliability > 0.0:
            if delta_age > config.freshness.delta_max_age_seconds:
                delta_freshness = "STALE"
                delta_reliability *= config.freshness.stale_reliability_multiplier
                reason_codes.append("STALE_DELTA_FEED")
            source_details["delta"] = {
                "available": True,
                "freshness": delta_freshness,
                "reliability": delta_reliability,
                "value": delta_val,
                "provenance": prov_str,
            }
        else:
            delta_available = False
            source_details["delta"] = {"available": False, "freshness": "UNAVAILABLE"}
            missing_sources.append("delta")

        # Family 5: Dealer Gamma / Volatility
        gamma_val = getattr(ctx, "gamma_value", None)
        gamma_prov = getattr(ctx, "gamma_provenance", "UNAVAILABLE")
        gamma_available = gamma_val is not None and str(gamma_prov).upper() != "UNAVAILABLE"
        gamma_freshness = "FRESH"
        gamma_reliability = 1.0

        if gamma_available:
            source_details["gamma"] = {
                "available": True,
                "freshness": gamma_freshness,
                "reliability": gamma_reliability,
                "value": gamma_val,
                "provenance": str(gamma_prov).upper(),
            }
        else:
            source_details["gamma"] = {"available": False, "freshness": "UNAVAILABLE"}
            missing_sources.append("gamma")

        # Calculate coverage count and status
        observed_count = sum(
            1 for k in ["underlying", "index", "sector", "delta", "gamma"]
            if source_details[k]["available"]
        )

        # ---------------------------------------------------------------------
        # 2. Strict Coverage Gating & Fail-Closed Rules
        # ---------------------------------------------------------------------
        if not underlying_available:
            coverage_audit = CoverageAudit(
                status="BLOCKED",
                observed_sources=observed_count,
                required_sources=config.total_coverage_sources,
                missing_sources=missing_sources,
                source_details=source_details,
            )
            reason_codes.append("MISSING_UNDERLYING_BARS")
            return MarketDriverResult(
                status=MarketDriverStatus.BLOCKED,
                coverage=coverage_audit,
                data_as_of=eval_time,
                knowledge_timestamp=eval_time,
                engine_version=config.engine_version,
                reason_codes=reason_codes,
            )

        if not index_available:
            coverage_audit = CoverageAudit(
                status="UNAVAILABLE",
                observed_sources=observed_count,
                required_sources=config.total_coverage_sources,
                missing_sources=missing_sources,
                source_details=source_details,
            )
            reason_codes.append("INDEX_BENCHMARK_UNAVAILABLE")
            return MarketDriverResult(
                status=MarketDriverStatus.UNAVAILABLE,
                coverage=coverage_audit,
                data_as_of=eval_time,
                knowledge_timestamp=eval_time,
                engine_version=config.engine_version,
                reason_codes=reason_codes,
            )

        # Minimum requirement: Underlying + Index + at least 1 other (minimum 3 of 5)
        if observed_count < config.min_coverage_sources:
            coverage_audit = CoverageAudit(
                status="INSUFFICIENT",
                observed_sources=observed_count,
                required_sources=config.total_coverage_sources,
                missing_sources=missing_sources,
                source_details=source_details,
            )
            reason_codes.append("INSUFFICIENT_EVIDENCE_COVERAGE")
            return MarketDriverResult(
                status=MarketDriverStatus.UNAVAILABLE,
                coverage=coverage_audit,
                data_as_of=eval_time,
                knowledge_timestamp=eval_time,
                engine_version=config.engine_version,
                reason_codes=reason_codes,
            )

        # Status classification
        if observed_count == config.total_coverage_sources:
            coverage_status = "COMPLETE"
            driver_status = MarketDriverStatus.AVAILABLE
            reason_codes.append("DRIVER_AVAILABLE_COMPLETE")
        else:
            coverage_status = "PARTIAL"
            driver_status = MarketDriverStatus.PARTIAL
            reason_codes.append("DRIVER_AVAILABLE_PARTIAL")

        coverage_audit = CoverageAudit(
            status=coverage_status,
            observed_sources=observed_count,
            required_sources=config.total_coverage_sources,
            missing_sources=missing_sources,
            source_details=source_details,
        )

        # ---------------------------------------------------------------------
        # 3. Continuous Multi-Factor Candidate Scoring
        # ---------------------------------------------------------------------
        # Candidates structure: archetype -> (raw_score, reliability, magnitude, direction, label)
        candidates: List[Dict[str, Any]] = []

        # Archetype 1 & 2: Index Risk-On / Risk-Off
        if index_available:
            score = float(market_alignment_score)
            clamped = max(-100.0, min(100.0, score))
            mag = abs(clamped) * index_reliability
            if clamped > 0:
                candidates.append({
                    "archetype": DriverArchetype.INDEX_RISK_ON,
                    "label": ARCHETYPE_LABELS[DriverArchetype.INDEX_RISK_ON],
                    "direction": DriverDirection.BULLISH,
                    "score": clamped,
                    "reliability": index_reliability,
                    "magnitude": mag,
                    "source_stage": "INDEX",
                })
            elif clamped < 0:
                candidates.append({
                    "archetype": DriverArchetype.INDEX_RISK_OFF,
                    "label": ARCHETYPE_LABELS[DriverArchetype.INDEX_RISK_OFF],
                    "direction": DriverDirection.BEARISH,
                    "score": clamped,
                    "reliability": index_reliability,
                    "magnitude": mag,
                    "source_stage": "INDEX",
                })

        # Archetype 3 & 4: Sector Leadership / Sector Lag
        if sector_available:
            score = float(sector_rs_score)
            clamped = max(-100.0, min(100.0, score))
            mag = abs(clamped) * sector_reliability
            if clamped > 0:
                candidates.append({
                    "archetype": DriverArchetype.SECTOR_LEADERSHIP,
                    "label": ARCHETYPE_LABELS[DriverArchetype.SECTOR_LEADERSHIP],
                    "direction": DriverDirection.BULLISH,
                    "score": clamped,
                    "reliability": sector_reliability,
                    "magnitude": mag,
                    "source_stage": "SECTOR",
                })
            elif clamped < 0:
                candidates.append({
                    "archetype": DriverArchetype.SECTOR_LAG,
                    "label": ARCHETYPE_LABELS[DriverArchetype.SECTOR_LAG],
                    "direction": DriverDirection.BEARISH,
                    "score": clamped,
                    "reliability": sector_reliability,
                    "magnitude": mag,
                    "source_stage": "SECTOR",
                })

        # Archetype 5 & 6: Gamma Pinning / Gamma Squeeze
        if gamma_available:
            val = float(gamma_val)
            atr = getattr(ctx, "atr", 1.0)
            if val > 0:
                # Positive gamma pinning
                mag = min(100.0, val) * gamma_reliability
                candidates.append({
                    "archetype": DriverArchetype.GAMMA_PINNING,
                    "label": ARCHETYPE_LABELS[DriverArchetype.GAMMA_PINNING],
                    "direction": DriverDirection.NEUTRAL,
                    "score": val,
                    "reliability": gamma_reliability,
                    "magnitude": mag,
                    "source_stage": "GAMMA",
                })
            elif val < 0:
                # Negative gamma squeeze acceleration
                mag = min(100.0, abs(val)) * gamma_reliability
                direction = DriverDirection.BEARISH if (market_alignment_score or 0.0) < 0 else DriverDirection.BULLISH
                candidates.append({
                    "archetype": DriverArchetype.GAMMA_SQUEEZE,
                    "label": ARCHETYPE_LABELS[DriverArchetype.GAMMA_SQUEEZE],
                    "direction": direction,
                    "score": val,
                    "reliability": gamma_reliability,
                    "magnitude": mag,
                    "source_stage": "GAMMA",
                })

        # Archetype 7: Delta Aggression
        # Strict provenance: Only ACTUAL_TRADE_AGGRESSOR or high-confidence ESTIMATED_BID_ASK
        if delta_available and prov_str in ("ACTUAL_TRADE_AGGRESSOR", "ESTIMATED_BID_ASK"):
            score = float(delta_val)
            clamped = max(-100.0, min(100.0, score))
            mag = abs(clamped) * delta_reliability
            direction = DriverDirection.BULLISH if clamped > 0 else DriverDirection.BEARISH
            candidates.append({
                "archetype": DriverArchetype.DELTA_AGGRESSION,
                "label": ARCHETYPE_LABELS[DriverArchetype.DELTA_AGGRESSION],
                "direction": direction,
                "score": clamped,
                "reliability": delta_reliability,
                "magnitude": mag,
                "source_stage": "DELTA",
            })

        # Archetype 8: VWAP Mean Reversion
        vwap = getattr(ctx, "vwap", 0.0)
        atr = getattr(ctx, "atr", 1.0)
        last_price = None
        if hasattr(ctx, "quote") and ctx.quote is not None:
            last_price = getattr(ctx.quote, "last_price", None)
        elif bars is not None and isinstance(bars, pd.DataFrame) and not bars.empty:
            last_price = float(bars.iloc[-1].get("close", 0.0))

        if vwap > 0 and atr > 0 and last_price is not None:
            dist = (last_price - vwap) / atr
            if abs(dist) >= 2.0 and bars is not None and len(bars) >= 2:
                prev_close = float(bars.iloc[-2].get("close", last_price))
                moving_toward_vwap = abs(last_price - vwap) < abs(prev_close - vwap)
                if moving_toward_vwap:
                    reversion_score = -dist * 25.0  # Opposes the stretch
                    clamped = max(-100.0, min(100.0, reversion_score))
                    mag = min(100.0, abs(dist) * 25.0)
                    direction = DriverDirection.BULLISH if dist < 0 else DriverDirection.BEARISH
                    candidates.append({
                        "archetype": DriverArchetype.VWAP_MEAN_REVERSION,
                        "label": ARCHETYPE_LABELS[DriverArchetype.VWAP_MEAN_REVERSION],
                        "direction": direction,
                        "score": clamped,
                        "reliability": 0.85,
                        "magnitude": mag * 0.85,
                        "source_stage": "VWAP",
                    })

        # Sort candidates descending by effective magnitude
        candidates.sort(key=lambda c: c["magnitude"], reverse=True)

        # ---------------------------------------------------------------------
        # 4. Primary Driver Selection with Hysteresis & Persistence
        # ---------------------------------------------------------------------
        primary_candidate = None
        if candidates and candidates[0]["magnitude"] >= config.thresholds.primary_activation_magnitude:
            primary_candidate = candidates[0]

        primary_driver: Optional[PrimaryDriver] = None
        hysteresis_hurdle = config.thresholds.hysteresis_delta

        if primary_candidate is not None:
            # Check incumbent from previous_result
            incumbent = previous_result.primary_driver if previous_result else None
            
            if incumbent is not None and incumbent.driver_id:
                incumbent_id = incumbent.driver_id
                incumbent_mag = incumbent.magnitude

                # Find candidate corresponding to incumbent
                incumbent_cand = next((c for c in candidates if c["archetype"].value == incumbent_id), None)
                current_incumbent_mag = incumbent_cand["magnitude"] if incumbent_cand else incumbent_mag * 0.90

                if primary_candidate["archetype"].value == incumbent_id:
                    # Incumbent remains highest
                    pers_state = PersistenceState.STABLE
                    if primary_candidate["magnitude"] > incumbent_mag + 5.0:
                        pers_state = PersistenceState.STRENGTHENING
                    elif primary_candidate["magnitude"] < incumbent_mag - 5.0:
                        pers_state = PersistenceState.WEAKENING

                    bars_active = incumbent.persistence.bars_active + 1
                    dur_sec = incumbent.persistence.duration_seconds + 300  # Assume 5m default bar
                    started_at = incumbent.persistence.started_at or eval_time

                    persistence = DriverPersistence(
                        state=pers_state,
                        duration_seconds=dur_sec,
                        started_at=started_at,
                        bars_active=bars_active,
                        minutes_active=round(dur_sec / 60.0, 1),
                        previous_primary_driver=incumbent.persistence.previous_primary_driver,
                        candidate_margin=round(primary_candidate["magnitude"] - current_incumbent_mag, 2),
                    )
                    strength = _classify_strength(primary_candidate["magnitude"], config)
                    primary_driver = PrimaryDriver(
                        driver_id=primary_candidate["archetype"].value,
                        label=primary_candidate["label"],
                        direction=primary_candidate["direction"],
                        strength=strength,
                        magnitude=primary_candidate["magnitude"],
                        persistence=persistence,
                    )
                else:
                    # New candidate differs from incumbent. Test Hysteresis:
                    margin = primary_candidate["magnitude"] - current_incumbent_mag
                    if margin >= hysteresis_hurdle:
                        # Hurdle exceeded: Transition to new primary driver
                        reason_codes.append(f"HYSTERESIS_REPLACED_INCUMBENT_{incumbent_id}")
                        persistence = DriverPersistence(
                            state=PersistenceState.NEW,
                            duration_seconds=0,
                            started_at=eval_time,
                            bars_active=1,
                            minutes_active=0.0,
                            previous_primary_driver=incumbent_id,
                            candidate_margin=round(margin, 2),
                        )
                        strength = _classify_strength(primary_candidate["magnitude"], config)
                        primary_driver = PrimaryDriver(
                            driver_id=primary_candidate["archetype"].value,
                            label=primary_candidate["label"],
                            direction=primary_candidate["direction"],
                            strength=strength,
                            magnitude=primary_candidate["magnitude"],
                            persistence=persistence,
                        )
                    else:
                        # Hurdle NOT met: Retain incumbent
                        reason_codes.append("HYSTERESIS_MAINTAINED")
                        bars_active = incumbent.persistence.bars_active + 1
                        dur_sec = incumbent.persistence.duration_seconds + 300
                        persistence = DriverPersistence(
                            state=PersistenceState.STABLE,
                            duration_seconds=dur_sec,
                            started_at=incumbent.persistence.started_at or eval_time,
                            bars_active=bars_active,
                            minutes_active=round(dur_sec / 60.0, 1),
                            previous_primary_driver=incumbent.persistence.previous_primary_driver,
                            candidate_margin=round(margin, 2),
                        )
                        strength = _classify_strength(current_incumbent_mag, config)
                        primary_driver = PrimaryDriver(
                            driver_id=incumbent_id,
                            label=incumbent.label,
                            direction=incumbent.direction,
                            strength=strength,
                            magnitude=current_incumbent_mag,
                            persistence=persistence,
                        )
            else:
                # No incumbent exists (first evaluation)
                persistence = DriverPersistence(
                    state=PersistenceState.NEW,
                    duration_seconds=0,
                    started_at=eval_time,
                    bars_active=1,
                    minutes_active=0.0,
                    previous_primary_driver=None,
                    candidate_margin=0.0,
                )
                strength = _classify_strength(primary_candidate["magnitude"], config)
                primary_driver = PrimaryDriver(
                    driver_id=primary_candidate["archetype"].value,
                    label=primary_candidate["label"],
                    direction=primary_candidate["direction"],
                    strength=strength,
                    magnitude=primary_candidate["magnitude"],
                    persistence=persistence,
                )

        # ---------------------------------------------------------------------
        # 5. Secondary Drivers Selection (Max 2, M >= 20.0)
        # ---------------------------------------------------------------------
        secondary_drivers: List[SecondaryDriver] = []
        if primary_driver:
            primary_id = primary_driver.driver_id
            for cand in candidates:
                if cand["archetype"].value == primary_id:
                    continue
                if cand["magnitude"] >= config.thresholds.secondary_activation_magnitude:
                    strength = _classify_strength(cand["magnitude"], config)
                    secondary_drivers.append(
                        SecondaryDriver(
                            driver_id=cand["archetype"].value,
                            label=cand["label"],
                            direction=cand["direction"],
                            strength=strength,
                            magnitude=cand["magnitude"],
                        )
                    )
                if len(secondary_drivers) >= config.max_secondary_drivers:
                    break

        # ---------------------------------------------------------------------
        # 6. Confirming vs Conflicting Evidence Tokens
        # ---------------------------------------------------------------------
        confirming_evidence: List[EvidenceToken] = []
        conflicting_evidence: List[EvidenceToken] = []

        primary_direction = primary_driver.direction if primary_driver else DriverDirection.NEUTRAL

        # Evidence Token Helper
        def add_token(
            token_id: str,
            label: str,
            source_stage: str,
            score: float,
            reliability: float,
            freshness: str,
            provenance: str,
        ) -> None:
            nonlocal confirming_evidence, conflicting_evidence
            if primary_direction == DriverDirection.BULLISH:
                if score >= 15.0:
                    cls = EvidenceClassification.CONFIRMING
                elif score <= -15.0:
                    cls = EvidenceClassification.CONFLICTING
                else:
                    cls = EvidenceClassification.NEUTRAL
            elif primary_direction == DriverDirection.BEARISH:
                if score <= -15.0:
                    cls = EvidenceClassification.CONFIRMING
                elif score >= 15.0:
                    cls = EvidenceClassification.CONFLICTING
                else:
                    cls = EvidenceClassification.NEUTRAL
            else:
                cls = EvidenceClassification.NEUTRAL

            token = EvidenceToken(
                evidence_id=token_id,
                label=label,
                source_stage=source_stage,
                event_timestamp=eval_time,
                knowledge_timestamp=eval_time,
                source=provenance,
                raw_value=score,
                normalized_score=score,
                reliability=reliability,
                freshness=freshness,
                provenance=provenance,
                classification=cls,
            )
            if cls == EvidenceClassification.CONFIRMING and len(confirming_evidence) < config.max_confirming_evidence:
                confirming_evidence.append(token)
            elif cls == EvidenceClassification.CONFLICTING and len(conflicting_evidence) < config.max_conflicting_evidence:
                conflicting_evidence.append(token)

        if index_available:
            add_token(
                "INDEX_BENCHMARK_ALIGNMENT",
                f"Index alignment score ({market_alignment_score:+.1f})",
                "INDEX",
                float(market_alignment_score),
                index_reliability,
                index_freshness,
                "INDEX_BENCHMARK",
            )

        if sector_available:
            add_token(
                "SECTOR_RELATIVE_STRENGTH",
                f"Sector relative strength ({sector_rs_score:+.1f})",
                "SECTOR",
                float(sector_rs_score),
                sector_reliability,
                sector_freshness,
                "SECTOR_ETF",
            )

        if delta_available:
            add_token(
                "ORDER_FLOW_DELTA",
                f"Delta aggression ({delta_val:+.1f})",
                "DELTA",
                float(delta_val),
                delta_reliability,
                delta_freshness,
                prov_str,
            )

        if gamma_available:
            gamma_label = "Positive dealer gamma (pinning)" if float(gamma_val) > 0 else "Negative dealer gamma (acceleration)"
            add_token(
                "DEALER_GAMMA_EXPOSURE",
                gamma_label,
                "GAMMA",
                float(gamma_val),
                gamma_reliability,
                gamma_freshness,
                str(gamma_prov).upper(),
            )

        # Structure token if structure is provided on context
        structure = getattr(ctx, "structure", None)
        if structure is not None:
            regime = getattr(structure, "regime", None)
            regime_str = str(regime.value if hasattr(regime, "value") else regime or "").upper()
            struct_score = 60.0 if regime_str == "BULLISH" else (-60.0 if regime_str == "BEARISH" else 0.0)
            if struct_score != 0.0:
                add_token(
                    "SMC_CONFIRMED_STRUCTURE",
                    f"Confirmed {regime_str.lower()} SMC structure",
                    "STRUCTURE",
                    struct_score,
                    1.0,
                    "FRESH",
                    "SMC_ANALYSIS",
                )

        # ---------------------------------------------------------------------
        # 7. Final Deterministic Result Packaging
        # ---------------------------------------------------------------------
        input_fingerprint = _fingerprint_inputs(
            symbol=getattr(ctx, "symbol", "UNKNOWN"),
            eval_ts=eval_time,
            inputs=source_details,
        )

        return MarketDriverResult(
            status=driver_status,
            primary_driver=primary_driver,
            secondary_drivers=secondary_drivers,
            confirming_evidence=confirming_evidence,
            conflicting_evidence=conflicting_evidence,
            coverage=coverage_audit,
            data_as_of=eval_time,
            knowledge_timestamp=eval_time,
            engine_version=config.engine_version,
            reason_codes=reason_codes,
            input_fingerprint=input_fingerprint,
        )
