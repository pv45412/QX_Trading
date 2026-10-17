"""Phase 6: Playbook A — Trend Pullback Continuation Evaluator.

Detects continuation setups where established directional structure retraces into
a validated Order Block, VWAP, FVG, or protected swing reference.

States: NO_SETUP, WATCH, ARMED. Emits NO trade executions.
"""

from typing import Any, Dict, List, Optional

from qx.config.rules_config import load_rules_config
from qx.models.rules import RuleResult, RuleSeverity, SignalState, TrendRegime
from qx.playbooks.base import BasePlaybookEvaluator, PlaybookEvaluation
from qx.playbooks.context import QXEvaluationContext


class TrendPullbackEvaluator(BasePlaybookEvaluator):
    playbook_id: str = "playbook_a_pullback"
    playbook_version: str = "1.0"

    def evaluate(self, ctx: QXEvaluationContext) -> PlaybookEvaluation:
        rules_cfg = ctx.rules_config or load_rules_config()
        cfg = rules_cfg.playbooks.get("playbook_a_pullback", {})
        min_dir_score = float(cfg.get("min_direction_score", 40.0))
        min_cov = float(cfg.get("direction_coverage_min", 0.75))
        max_dist_atr = float(cfg.get("max_distance_to_zone_atr", 1.50))

        rule_results: List[RuleResult] = []
        source_ob_ids: List[str] = []
        source_struct_ids: List[str] = []
        source_pivot_ids: List[str] = []

        trend_regime = ctx.market_regime.trend
        dir_score = ctx.direction.direction_score
        dir_cov = ctx.direction.direction_evidence_coverage
        dir_label = ctx.direction.direction_label

        struct_state = "NEUTRAL"
        struct_invalidated = False
        if ctx.structure_result is not None:
            if hasattr(ctx.structure_result, "regime"):
                s_val = getattr(ctx.structure_result, "regime")
                struct_state = s_val.value if hasattr(s_val, "value") else str(s_val)
            elif hasattr(ctx.structure_result, "state"):
                s_val = getattr(ctx.structure_result, "state")
                struct_state = s_val.value if hasattr(s_val, "value") else str(s_val)
            elif isinstance(ctx.structure_result, dict):
                state_val = ctx.structure_result.get("regime", ctx.structure_result.get("state"))
                if state_val is not None:
                    struct_state = state_val.value if hasattr(state_val, "value") else str(state_val)
            if hasattr(ctx.structure_result, "invalidated"):
                struct_invalidated = bool(getattr(ctx.structure_result, "invalidated"))

        struct_state = struct_state.upper()

        # Rule 1: Regime alignment
        r1_passed = trend_regime in (TrendRegime.TREND_UP, TrendRegime.TREND_DOWN)
        rule_results.append(
            RuleResult(
                rule_id="QX-PB-A-001",
                category="REGIME",
                required_value="TREND_UP or TREND_DOWN",
                observed_value=trend_regime.value,
                passed=r1_passed,
                severity=RuleSeverity.HARD,
                detail=f"Trend regime alignment: {trend_regime.value}",
            )
        )

        # Rule 2: Evidence Coverage
        r2_passed = dir_cov >= min_cov
        rule_results.append(
            RuleResult(
                rule_id="QX-PB-A-002",
                category="COVERAGE",
                required_value=f">= {min_cov}",
                observed_value=round(dir_cov, 3),
                passed=r2_passed,
                severity=RuleSeverity.HARD,
                detail=f"Evidence coverage check: {dir_cov:.3f}",
            )
        )

        # Rule 3: Confirmed Structure & Non-invalidated
        r3_passed = (struct_state in ("BULLISH", "BEARISH")) and not struct_invalidated
        rule_results.append(
            RuleResult(
                rule_id="QX-PB-A-003",
                category="STRUCTURE",
                required_value="BULLISH or BEARISH non-invalidated",
                observed_value=f"{struct_state} (invalidated={struct_invalidated})",
                passed=r3_passed,
                severity=RuleSeverity.HARD,
                detail=f"Market structure state: {struct_state}",
            )
        )

        if not (r1_passed and r2_passed and r3_passed):
            if not r3_passed:
                reason_code = "NO_STRUCTURAL_CONTEXT"
            elif not r1_passed:
                reason_code = "REGIME_NOT_TRENDING"
            else:
                reason_code = "INSUFFICIENT_EVIDENCE_COVERAGE"
            return PlaybookEvaluation(
                playbook_id=self.playbook_id,
                playbook_version=self.playbook_version,
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction="NEUTRAL",
                state=SignalState.NO_SETUP,
                setup_detected=False,
                reason_code=reason_code,
                publication_state=ctx.publication_state,
                direction_score=dir_score,
                direction_evidence_coverage=dir_cov,
                market_regime=ctx.market_regime,
                rule_results=rule_results,
                event_timestamp=ctx.event_timestamp,
                knowledge_timestamp=ctx.knowledge_timestamp,
                config_version=rules_cfg.version,
            )

        # Determine directional bias
        is_bullish = trend_regime == TrendRegime.TREND_UP and struct_state == "BULLISH" and dir_score >= min_dir_score
        is_bearish = trend_regime == TrendRegime.TREND_DOWN and struct_state == "BEARISH" and dir_score <= -min_dir_score

        if not (is_bullish or is_bearish):
            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-A-004",
                    category="DIRECTION",
                    required_value=f"score >= {min_dir_score} (bullish) or <= -{min_dir_score} (bearish)",
                    observed_value=dir_score,
                    passed=False,
                    severity=RuleSeverity.HARD,
                    detail="Direction score misaligned with trend regime",
                )
            )
            return PlaybookEvaluation(
                playbook_id=self.playbook_id,
                playbook_version=self.playbook_version,
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction="NEUTRAL",
                state=SignalState.NO_SETUP,
                setup_detected=False,
                reason_code="DIRECTION_MISALIGNED",
                publication_state=ctx.publication_state,
                direction_score=dir_score,
                direction_evidence_coverage=dir_cov,
                market_regime=ctx.market_regime,
                rule_results=rule_results,
                event_timestamp=ctx.event_timestamp,
                knowledge_timestamp=ctx.knowledge_timestamp,
                config_version=rules_cfg.version,
            )

        pb_direction = "BULLISH" if is_bullish else "BEARISH"
        price = ctx.latest_bar.get("close", ctx.latest_bar.get("price", 0.0))
        atr = ctx.atr or 1.0

        # Evaluate structural locations for pullback: Order Blocks, VWAP, FVGs
        valid_obs = []
        for ob in ctx.order_blocks:
            ob_state = getattr(ob, "state", None) or (ob.get("state") if isinstance(ob, dict) else "CANDIDATE")
            ob_state_str = ob_state.value if hasattr(ob_state, "value") else str(ob_state)
            ob_type = getattr(ob, "type", None) or getattr(ob, "direction", None)
            if ob_type is None and isinstance(ob, dict):
                ob_type = ob.get("type", ob.get("direction", ""))
            ob_type_str = ob_type.value if hasattr(ob_type, "value") else str(ob_type)

            # Filter non-expired and non-invalidated Order Blocks
            if ob_state_str in ("VALIDATED", "MITIGATED"):
                if (is_bullish and "BULLISH" in ob_type_str.upper()) or (is_bearish and "BEARISH" in ob_type_str.upper()):
                    valid_obs.append(ob)

        has_ob = len(valid_obs) > 0
        has_vwap = ctx.vwap is not None
        has_fvg = len(ctx.fvgs) > 0

        has_structural_target = has_ob or has_vwap or has_fvg

        rule_results.append(
            RuleResult(
                rule_id="QX-PB-A-005",
                category="RETRACEMENT_TARGET",
                required_value="Valid OB, VWAP, or FVG reference present",
                observed_value=f"OBs={len(valid_obs)}, VWAP={ctx.vwap}, FVGs={len(ctx.fvgs)}",
                passed=has_structural_target,
                severity=RuleSeverity.HARD,
                detail="Presence of structural retracement targets",
            )
        )

        if not has_structural_target:
            return PlaybookEvaluation(
                playbook_id=self.playbook_id,
                playbook_version=self.playbook_version,
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction=pb_direction,
                state=SignalState.NO_SETUP,
                setup_detected=False,
                reason_code="NO_RETRACEMENT_TARGET",
                publication_state=ctx.publication_state,
                direction_score=dir_score,
                direction_evidence_coverage=dir_cov,
                market_regime=ctx.market_regime,
                rule_results=rule_results,
                event_timestamp=ctx.event_timestamp,
                knowledge_timestamp=ctx.knowledge_timestamp,
                config_version=rules_cfg.version,
            )

        # Check zone entry / proximity
        in_zone = False
        approaching_zone = False
        zone_prox_details = []
        target_candidates = []

        if valid_obs:
            for ob in valid_obs:
                ob_id = getattr(ob, "ob_id", None) or getattr(ob, "order_block_id", None)
                if ob_id is None and isinstance(ob, dict):
                    ob_id = ob.get("ob_id", ob.get("order_block_id", "ob_1"))
                source_ob_ids.append(str(ob_id))
                px_prox = getattr(ob, "proximal_price", None) or (ob.get("proximal_price") if isinstance(ob, dict) else price)
                px_dist = getattr(ob, "distal_price", None) or (ob.get("distal_price") if isinstance(ob, dict) else price)

                target_candidates.append(float(px_prox))
                target_candidates.append(float(px_dist))

                low_z = min(px_prox, px_dist)
                high_z = max(px_prox, px_dist)

                if low_z <= price <= high_z:
                    in_zone = True
                    zone_prox_details.append(f"Price ({price}) inside OB {ob_id} [{low_z:.2f} - {high_z:.2f}]")
                elif abs(price - px_prox) <= max_dist_atr * atr or abs(price - px_dist) <= max_dist_atr * atr:
                    approaching_zone = True
                    zone_prox_details.append(f"Price ({price}) approaching OB {ob_id}")

        if has_vwap and not in_zone:
            target_candidates.append(float(ctx.vwap))
            if abs(price - ctx.vwap) <= 0.5 * atr:
                in_zone = True
                zone_prox_details.append(f"Price ({price}) at VWAP ({ctx.vwap:.2f})")
            elif abs(price - ctx.vwap) <= max_dist_atr * atr:
                approaching_zone = True
                zone_prox_details.append(f"Price ({price}) approaching VWAP ({ctx.vwap:.2f})")

        if has_fvg and not in_zone:
            for fvg in ctx.fvgs:
                fvg_id = getattr(fvg, "id", None) or (fvg.get("id") if isinstance(fvg, dict) else "fvg_1")
                px_prox = float(getattr(fvg, "proximal_price", None) or (fvg.get("proximal_price") if isinstance(fvg, dict) else price))
                px_dist = float(getattr(fvg, "distal_price", None) or (fvg.get("distal_price") if isinstance(fvg, dict) else price))
                target_candidates.append(px_prox)
                target_candidates.append(px_dist)
                low_z = min(px_prox, px_dist)
                high_z = max(px_prox, px_dist)
                if low_z <= price <= high_z:
                    in_zone = True
                    zone_prox_details.append(f"Price ({price}) inside FVG {fvg_id} [{low_z:.2f} - {high_z:.2f}]")
                elif abs(price - px_prox) <= max_dist_atr * atr or abs(price - px_dist) <= max_dist_atr * atr:
                    approaching_zone = True
                    zone_prox_details.append(f"Price ({price}) approaching FVG {fvg_id}")

        confluence_count = (1 if valid_obs else 0) + (1 if has_vwap else 0) + (1 if has_fvg else 0)
        quality_components = {
            "confluence_score": round(confluence_count * 33.3, 1),
            "direction_strength": round(abs(dir_score), 1),
            "evidence_coverage": round(dir_cov * 100.0, 1),
        }

        if in_zone:
            eval_state = SignalState.ARMED
            reason_code = "SETUP_FORMED_WAITING_FOR_TRIGGER"
            # Deterministic trigger level: Zone proximal boundary
            primary_ob = valid_obs[0] if valid_obs else None
            if primary_ob:
                ob_id = getattr(primary_ob, "ob_id", None) or getattr(primary_ob, "order_block_id", None)
                if ob_id is None and isinstance(primary_ob, dict):
                    ob_id = primary_ob.get("ob_id", primary_ob.get("order_block_id", "ob_1"))
                ob_id_val = str(ob_id or "ob_1")
                px_prox = float(getattr(primary_ob, "proximal_price", None) or (primary_ob.get("proximal_price") if isinstance(primary_ob, dict) else price))
                px_dist = float(getattr(primary_ob, "distal_price", None) or (primary_ob.get("distal_price") if isinstance(primary_ob, dict) else price))
                trig_know_ts = str(getattr(primary_ob, "candidate_available_at", None) or getattr(primary_ob, "knowledge_timestamp", None) or (primary_ob.get("candidate_available_at") if isinstance(primary_ob, dict) else None) or (primary_ob.get("knowledge_timestamp") if isinstance(primary_ob, dict) else None) or ctx.knowledge_timestamp or ctx.event_timestamp)
                trigger_px = px_prox
                trig_src_type = "ZONE_PROXIMAL_BOUNDARY"
                trig_src_id = ob_id_val
                inval_px = px_dist
                inval_src_type = "ZONE_DISTAL_BOUNDARY"
                inval_src_id = ob_id_val
            elif has_fvg and ctx.fvgs:
                fvg = ctx.fvgs[0]
                fvg_id_val = str(getattr(fvg, "id", None) or (fvg.get("id") if isinstance(fvg, dict) else "fvg_1"))
                px_prox = float(getattr(fvg, "proximal_price", None) or (fvg.get("proximal_price") if isinstance(fvg, dict) else price))
                px_dist = float(getattr(fvg, "distal_price", None) or (fvg.get("distal_price") if isinstance(fvg, dict) else price - (1.0 * atr if is_bullish else -1.0 * atr)))
                trig_know_ts = str(getattr(fvg, "knowledge_timestamp", None) or (fvg.get("knowledge_timestamp") if isinstance(fvg, dict) else None) or ctx.knowledge_timestamp or ctx.event_timestamp)
                trigger_px = px_prox
                trig_src_type = "FVG_PROXIMAL_BOUNDARY"
                trig_src_id = fvg_id_val
                inval_px = px_dist
                inval_src_type = "FVG_DISTAL_BOUNDARY"
                inval_src_id = fvg_id_val
            else:
                vwap_val = float(ctx.vwap) if ctx.vwap is not None else price
                trig_know_ts = ctx.knowledge_timestamp or ctx.event_timestamp
                trigger_px = vwap_val
                trig_src_type = "VWAP_LEVEL"
                trig_src_id = "vwap_ref"
                inval_px = vwap_val - (1.0 * atr if is_bullish else -1.0 * atr)
                inval_src_type = "VWAP_BUFFER_BOUNDARY"
                inval_src_id = "vwap_ref"
                px_prox = trigger_px

            trigger_def = (
                f"5m candle close above local reclaim level ({trigger_px:.2f})"
                if is_bullish
                else f"5m candle close below local breakdown level ({trigger_px:.2f})"
            )

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-A-006",
                    category="ZONE_ENTRY",
                    required_value="Price inside structural zone",
                    observed_value=price,
                    passed=True,
                    severity=RuleSeverity.HARD,
                    detail="; ".join(zone_prox_details) or "Price entered qualifying structural zone",
                )
            )
        elif approaching_zone:
            eval_state = SignalState.WATCH
            reason_code = "WAITING_FOR_PULLBACK"
            trigger_def = "Awaiting price retracement entry into structural zone"
            trigger_px = None
            trig_src_type = ""
            trig_src_id = ""
            inval_px = None
            inval_src_type = ""
            inval_src_id = ""

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-A-006",
                    category="ZONE_ENTRY",
                    required_value="Price inside structural zone",
                    observed_value=price,
                    passed=False,
                    severity=RuleSeverity.SOFT,
                    detail="; ".join(zone_prox_details) or "Price approaching structural zone",
                )
            )
        else:
            eval_state = SignalState.NO_SETUP
            reason_code = "PRICE_NOT_NEAR_STRUCTURAL_TARGET"
            trigger_def = ""
            trigger_px = None
            trig_src_type = ""
            trig_src_id = ""
            inval_px = None
            inval_src_type = ""
            inval_src_id = ""

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-A-006",
                    category="ZONE_ENTRY",
                    required_value="Price near or inside structural zone",
                    observed_value=price,
                    passed=False,
                    severity=RuleSeverity.HARD,
                    detail="Price far from structural zone",
                )
            )

        return PlaybookEvaluation(
            playbook_id=self.playbook_id,
            playbook_version=self.playbook_version,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            direction=pb_direction,
            state=eval_state,
            setup_detected=(eval_state in (SignalState.WATCH, SignalState.ARMED)),
            reason_code=reason_code,
            setup_quality_components=quality_components,
            trigger_definition=trigger_def,
            trigger_price=trigger_px,
            trigger_source_type=trig_src_type,
            trigger_source_id=trig_src_id,
            trigger_knowledge_timestamp=trig_know_ts if eval_state == SignalState.ARMED else (ctx.knowledge_timestamp or ctx.event_timestamp),
            invalidation_price=inval_px,
            invalidation_source_type=inval_src_type,
            invalidation_source_id=inval_src_id,
            invalidation_knowledge_timestamp=trig_know_ts if eval_state == SignalState.ARMED else (ctx.knowledge_timestamp or ctx.event_timestamp),
            structural_target_candidates=target_candidates,
            publication_state=ctx.publication_state,
            direction_score=dir_score,
            direction_evidence_coverage=dir_cov,
            market_regime=ctx.market_regime,
            source_order_block_ids=source_ob_ids,
            source_structure_event_ids=source_struct_ids,
            source_pivot_ids=source_pivot_ids,
            rule_results=rule_results,
            event_timestamp=ctx.event_timestamp,
            knowledge_timestamp=ctx.knowledge_timestamp,
            config_version=rules_cfg.version,
        )
