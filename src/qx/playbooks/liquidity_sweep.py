"""Phase 6: Playbook B — Liquidity Sweep + Reclaim Evaluator.

Detects reversal/rotation setups where price runs identifiable liquidity levels
(PDH, PDL, SWING_HIGH, SWING_LOW, EQH, EQL, ORB_HIGH, ORB_LOW), rejects the level,
and forms a potential reclaim condition.

Supports countertrend setups (does NOT require prior directional score alignment).
States: NO_SETUP, WATCH, ARMED. Emits NO trade executions.
"""

from typing import Any, Dict, List, Optional

from qx.config.rules_config import load_rules_config
from qx.models.rules import RuleResult, RuleSeverity, SignalState
from qx.playbooks.base import BasePlaybookEvaluator, PlaybookEvaluation
from qx.playbooks.context import QXEvaluationContext


class LiquiditySweepEvaluator(BasePlaybookEvaluator):
    playbook_id: str = "playbook_b_liquidity_sweep"
    playbook_version: str = "1.0"

    def evaluate(self, ctx: QXEvaluationContext) -> PlaybookEvaluation:
        rules_cfg = ctx.rules_config or load_rules_config()
        cfg = rules_cfg.playbooks.get("playbook_b_liquidity_sweep", {})
        max_approach_atr = float(cfg.get("max_approach_distance_atr", 1.50))
        min_sweep_atr = float(cfg.get("min_sweep_distance_atr", 0.10))
        inval_atr_buffer = float(cfg.get("invalidation_atr_buffer", 0.20))

        rule_results: List[RuleResult] = []
        source_pivot_ids: List[str] = []

        price = ctx.latest_bar.get("close", ctx.latest_bar.get("price", 0.0))
        high_px = ctx.latest_bar.get("high", price)
        low_px = ctx.latest_bar.get("low", price)
        atr = ctx.atr or 1.0

        dir_score = ctx.direction.direction_score
        dir_cov = ctx.direction.direction_evidence_coverage

        session_levels = ctx.session_levels or {}

        # Collect liquidity level candidates
        # Formats: {"type": "PDL", "price": 5000.0, "id": "pdl_1"}
        liquidity_levels = []

        for level in ctx.liquidity_levels:
            role = str(getattr(level, "role", ""))
            pool_type = str(getattr(level, "pool_type", ""))
            level_type = {
                "PROTECTED_HIGH": "SWING_HIGH",
                "PROTECTED_LOW": "SWING_LOW",
            }.get(role, pool_type)
            if level_type not in {"SWING_HIGH", "SWING_LOW", "EQH", "EQL"}:
                continue
            liquidity_levels.append(
                {
                    "type": level_type,
                    "price": float(level.price),
                    "id": str(
                        getattr(level, "pivot_id", "")
                        or getattr(level, "pool_id", "")
                    ),
                    "source_pivot_ids": list(
                        getattr(level, "source_pivot_ids", [])
                        or [getattr(level, "pivot_id", "")]
                    ),
                    "knowledge_timestamp": str(
                        getattr(level, "knowledge_timestamp", "") or ""
                    ),
                }
            )

        if "PDH" in session_levels and session_levels["PDH"] is not None:
            liquidity_levels.append({"type": "PDH", "price": float(session_levels["PDH"]), "id": "pdh_level"})
        if "PDL" in session_levels and session_levels["PDL"] is not None:
            liquidity_levels.append({"type": "PDL", "price": float(session_levels["PDL"]), "id": "pdl_level"})

        if "SWING_HIGH" in session_levels and session_levels["SWING_HIGH"] is not None:
            liquidity_levels.append({"type": "SWING_HIGH", "price": float(session_levels["SWING_HIGH"]), "id": "swing_high_level"})
        if "SWING_LOW" in session_levels and session_levels["SWING_LOW"] is not None:
            liquidity_levels.append({"type": "SWING_LOW", "price": float(session_levels["SWING_LOW"]), "id": "swing_low_level"})

        if "EQH" in session_levels and session_levels["EQH"] is not None:
            liquidity_levels.append({"type": "EQH", "price": float(session_levels["EQH"]), "id": "eqh_level"})
        if "EQL" in session_levels and session_levels["EQL"] is not None:
            liquidity_levels.append({"type": "EQL", "price": float(session_levels["EQL"]), "id": "eql_level"})

        if "ORB_HIGH" in session_levels and session_levels["ORB_HIGH"] is not None:
            liquidity_levels.append({"type": "ORB_HIGH", "price": float(session_levels["ORB_HIGH"]), "id": "orb_high_level"})
        if "ORB_LOW" in session_levels and session_levels["ORB_LOW"] is not None:
            liquidity_levels.append({"type": "ORB_LOW", "price": float(session_levels["ORB_LOW"]), "id": "orb_low_level"})

        # Rule 1: Deterministic liquidity levels exist
        has_levels = len(liquidity_levels) > 0
        rule_results.append(
            RuleResult(
                rule_id="QX-PB-B-001",
                category="LIQUIDITY_LEVEL",
                required_value="Deterministic liquidity levels present",
                observed_value=f"Found {len(liquidity_levels)} levels",
                passed=has_levels,
                severity=RuleSeverity.HARD,
                detail="Presence of deterministic liquidity reference levels",
            )
        )

        if not has_levels:
            return PlaybookEvaluation(
                playbook_id=self.playbook_id,
                playbook_version=self.playbook_version,
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction="NEUTRAL",
                state=SignalState.NO_SETUP,
                setup_detected=False,
                reason_code="NO_LIQUIDITY_LEVELS",
                publication_state=ctx.publication_state,
                direction_score=dir_score,
                direction_evidence_coverage=dir_cov,
                market_regime=ctx.market_regime,
                rule_results=rule_results,
                event_timestamp=ctx.event_timestamp,
                knowledge_timestamp=ctx.knowledge_timestamp,
                config_version=rules_cfg.version,
            )

        # Check for sweeps vs approaches
        bullish_sweep = None
        bearish_sweep = None
        bullish_approach = None
        bearish_approach = None

        for lvl in liquidity_levels:
            lvl_type = lvl["type"]
            lvl_px = lvl["price"]
            lvl_id = lvl["id"]

            # Downside liquidity (PDL, SWING_LOW, EQL, ORB_LOW)
            if lvl_type in ("PDL", "SWING_LOW", "EQL", "ORB_LOW"):
                if low_px < lvl_px:
                    sweep_dist = (lvl_px - low_px) / atr
                    if sweep_dist >= min_sweep_atr:
                        bullish_sweep = {
                            "level": lvl,
                            "sweep_dist_atr": sweep_dist,
                            "reclaim_condition": price >= lvl_px - 0.2 * atr,
                        }
                        source_pivot_ids.extend(
                            source_id for source_id in lvl.get("source_pivot_ids", [lvl_id]) if source_id
                        )
                elif abs(price - lvl_px) <= max_approach_atr * atr:
                    bullish_approach = {"level": lvl, "distance_atr": abs(price - lvl_px) / atr}
                    source_pivot_ids.extend(
                        source_id for source_id in lvl.get("source_pivot_ids", [lvl_id]) if source_id
                    )

            # Upside liquidity (PDH, SWING_HIGH, EQH, ORB_HIGH)
            if lvl_type in ("PDH", "SWING_HIGH", "EQH", "ORB_HIGH"):
                if high_px > lvl_px:
                    sweep_dist = (high_px - lvl_px) / atr
                    if sweep_dist >= min_sweep_atr:
                        bearish_sweep = {
                            "level": lvl,
                            "sweep_dist_atr": sweep_dist,
                            "reclaim_condition": price <= lvl_px + 0.2 * atr,
                        }
                        source_pivot_ids.extend(
                            source_id for source_id in lvl.get("source_pivot_ids", [lvl_id]) if source_id
                        )
                elif abs(price - lvl_px) <= max_approach_atr * atr:
                    bearish_approach = {"level": lvl, "distance_atr": abs(price - lvl_px) / atr}
                    source_pivot_ids.extend(
                        source_id for source_id in lvl.get("source_pivot_ids", [lvl_id]) if source_id
                    )

        # Determine state
        if bullish_sweep or bearish_sweep:
            eval_state = SignalState.ARMED
            reason_code = "SETUP_FORMED_WAITING_FOR_TRIGGER"
            if bullish_sweep:
                pb_direction = "BULLISH"
                swp = bullish_sweep
                lvl_info = swp["level"]
                trigger_def = f"5m CLOSE reclaim above swept {lvl_info['type']} ({lvl_info['price']:.2f})"
                trigger_px = float(lvl_info["price"])
                trig_src_type = "RECLAIMED_LIQUIDITY_LEVEL"
                trig_src_id = str(lvl_info["id"])
                inval_px = float(low_px - inval_atr_buffer * atr)
                inval_src_type = "SWEEP_EXTREME_PLUS_BUFFER"
                inval_src_id = str(lvl_info["id"])
                target_candidates = [lvl_info["price"] + 2.0 * atr]
                detail_msg = f"Bullish sweep of {lvl_info['type']} ({lvl_info['price']:.2f}) by {swp['sweep_dist_atr']:.2f} ATR"
            else:
                pb_direction = "BEARISH"
                swp = bearish_sweep
                lvl_info = swp["level"]
                trigger_def = f"5m CLOSE reclaim below swept {lvl_info['type']} ({lvl_info['price']:.2f})"
                trigger_px = float(lvl_info["price"])
                trig_src_type = "RECLAIMED_LIQUIDITY_LEVEL"
                trig_src_id = str(lvl_info["id"])
                inval_px = float(high_px + inval_atr_buffer * atr)
                inval_src_type = "SWEEP_EXTREME_PLUS_BUFFER"
                inval_src_id = str(lvl_info["id"])
                target_candidates = [lvl_info["price"] - 2.0 * atr]
                detail_msg = f"Bearish sweep of {lvl_info['type']} ({lvl_info['price']:.2f}) by {swp['sweep_dist_atr']:.2f} ATR"
            level_knowledge_timestamp = str(
                lvl_info.get("knowledge_timestamp")
                or ctx.knowledge_timestamp
                or ctx.event_timestamp
            )

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-B-002",
                    category="LIQUIDITY_SWEEP",
                    required_value=f"Sweep distance >= {min_sweep_atr} ATR",
                    observed_value=price,
                    passed=True,
                    severity=RuleSeverity.HARD,
                    detail=detail_msg,
                )
            )
        elif bullish_approach or bearish_approach:
            eval_state = SignalState.WATCH
            reason_code = "WAITING_FOR_SWEEP"
            if bullish_approach:
                pb_direction = "BULLISH"
                app = bullish_approach
                lvl_info = app["level"]
                detail_msg = f"Price approaching downside liquidity {lvl_info['type']} ({lvl_info['price']:.2f})"
            else:
                pb_direction = "BEARISH"
                app = bearish_approach
                lvl_info = app["level"]
                detail_msg = f"Price approaching upside liquidity {lvl_info['type']} ({lvl_info['price']:.2f})"

            trigger_def = f"Awaiting sweep of {lvl_info['type']} level"
            trigger_px = None
            trig_src_type = ""
            trig_src_id = ""
            inval_px = None
            inval_src_type = ""
            inval_src_id = ""
            target_candidates = [lvl_info["price"]]
            level_knowledge_timestamp = str(
                lvl_info.get("knowledge_timestamp")
                or ctx.knowledge_timestamp
                or ctx.event_timestamp
            )

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-B-002",
                    category="LIQUIDITY_SWEEP",
                    required_value="Liquidity level sweep",
                    observed_value=price,
                    passed=False,
                    severity=RuleSeverity.SOFT,
                    detail=detail_msg,
                )
            )
        else:
            eval_state = SignalState.NO_SETUP
            reason_code = "NO_LIQUIDITY_APPROACH_OR_SWEEP"
            pb_direction = "NEUTRAL"
            trigger_def = ""
            trigger_px = None
            trig_src_type = ""
            trig_src_id = ""
            inval_px = None
            inval_src_type = ""
            inval_src_id = ""
            target_candidates = []
            level_knowledge_timestamp = ctx.knowledge_timestamp or ctx.event_timestamp

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-B-002",
                    category="LIQUIDITY_SWEEP",
                    required_value="Liquidity level approach or sweep",
                    observed_value=price,
                    passed=False,
                    severity=RuleSeverity.HARD,
                    detail="No liquidity level in approach range or swept",
                )
            )

        quality_components = {
            "sweep_depth_quality": round(min_sweep_atr * 100.0, 1),
            "evidence_coverage": round(dir_cov * 100.0, 1),
        }

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
            trigger_knowledge_timestamp=level_knowledge_timestamp,
            invalidation_price=inval_px,
            invalidation_source_type=inval_src_type,
            invalidation_source_id=inval_src_id,
            invalidation_knowledge_timestamp=level_knowledge_timestamp,
            structural_target_candidates=target_candidates,
            publication_state=ctx.publication_state,
            direction_score=dir_score,
            direction_evidence_coverage=dir_cov,
            market_regime=ctx.market_regime,
            source_pivot_ids=source_pivot_ids,
            rule_results=rule_results,
            event_timestamp=ctx.event_timestamp,
            knowledge_timestamp=ctx.knowledge_timestamp,
            config_version=rules_cfg.version,
        )
