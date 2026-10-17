"""Phase 6: Playbook C — Opening Range Breakout (ORB) Evaluator.

Detects structured opening-range breakout setups respecting completed RTH opening ranges.

States: NO_SETUP, WATCH, ARMED. Emits NO trade executions.
"""

from typing import Any, Dict, List, Optional

from qx.config.rules_config import load_rules_config
from qx.models.rules import RuleResult, RuleSeverity, SignalState, SessionRegime
from qx.playbooks.base import BasePlaybookEvaluator, PlaybookEvaluation
from qx.playbooks.context import QXEvaluationContext


class OpeningRangeBreakoutEvaluator(BasePlaybookEvaluator):
    playbook_id: str = "playbook_c_orb_breakout"
    playbook_version: str = "1.0"

    def evaluate(self, ctx: QXEvaluationContext) -> PlaybookEvaluation:
        rules_cfg = ctx.rules_config or load_rules_config()
        cfg = rules_cfg.playbooks.get("playbook_c_orb_breakout", {})
        orb_minutes = int(cfg.get("orb_minutes", 15))
        min_cov = float(cfg.get("direction_coverage_min", 0.75))
        max_ext_atr = float(cfg.get("max_extension_atr", 2.00))

        rule_results: List[RuleResult] = []

        dir_score = ctx.direction.direction_score
        dir_cov = ctx.direction.direction_evidence_coverage
        session_levels = ctx.session_levels or {}

        orb_high = session_levels.get("ORB_HIGH")
        orb_low = session_levels.get("ORB_LOW")
        orb_complete = session_levels.get("ORB_COMPLETE", False)

        price = ctx.latest_bar.get("close", ctx.latest_bar.get("price", 0.0))
        high_px = ctx.latest_bar.get("high", price)
        low_px = ctx.latest_bar.get("low", price)
        atr = ctx.atr or 1.0

        # Rule 1: Evidence Coverage
        r1_passed = dir_cov >= min_cov
        rule_results.append(
            RuleResult(
                rule_id="QX-PB-C-001",
                category="COVERAGE",
                required_value=f">= {min_cov}",
                observed_value=round(dir_cov, 3),
                passed=r1_passed,
                severity=RuleSeverity.HARD,
                detail=f"Evidence coverage check: {dir_cov:.3f}",
            )
        )

        # Rule 2: ORB Window Complete
        rule_results.append(
            RuleResult(
                rule_id="QX-PB-C-002",
                category="ORB_WINDOW",
                required_value=f"RTH {orb_minutes}m window complete",
                observed_value=f"orb_complete={orb_complete}, high={orb_high}, low={orb_low}",
                passed=orb_complete and (orb_high is not None) and (orb_low is not None),
                severity=RuleSeverity.HARD,
                detail=f"RTH {orb_minutes}-minute Opening Range completion status",
            )
        )

        if not (r1_passed and orb_complete and orb_high is not None and orb_low is not None):
            reason_code = (
                "INSUFFICIENT_EVIDENCE_COVERAGE"
                if not r1_passed
                else "ORB_WINDOW_INCOMPLETE"
            )
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

        orb_high_val = float(orb_high)
        orb_low_val = float(orb_low)
        orb_mid = (orb_high_val + orb_low_val) / 2.0
        orb_range = orb_high_val - orb_low_val
        orb_range_atr = orb_range / atr if atr > 0 else 1.0

        quality_components = {
            "orb_range_atr": round(orb_range_atr, 2),
            "direction_strength": round(abs(dir_score), 1),
            "evidence_coverage": round(dir_cov * 100.0, 1),
        }

        # Calculate extension metrics
        extension_high_atr = (high_px - orb_high_val) / atr if high_px > orb_high_val else 0.0
        extension_low_atr = (orb_low_val - low_px) / atr if low_px < orb_low_val else 0.0
        extension_from_boundary_atr = max(extension_high_atr, extension_low_atr)

        quality_components = {
            "orb_range_atr": round(orb_range_atr, 2),
            "extension_from_boundary_atr": round(extension_from_boundary_atr, 2),
            "direction_strength": round(abs(dir_score), 1),
            "evidence_coverage": round(dir_cov * 100.0, 1),
        }

        target_candidates = [orb_high_val + 1.5 * orb_range, orb_low_val - 1.5 * orb_range]

        # Determine breakout setup state
        if high_px > orb_high_val and extension_high_atr <= max_ext_atr and dir_score >= -20.0:
            eval_state = SignalState.ARMED
            reason_code = "SETUP_FORMED_WAITING_FOR_TRIGGER"
            pb_direction = "BULLISH"
            trigger_def = f"5m confirmed body close above OR High ({orb_high_val:.2f})"
            trigger_px = float(orb_high_val)
            trig_src_type = "ORB_HIGH_BOUNDARY"
            trig_src_id = "orb_high"
            inval_px = float(orb_mid)
            inval_src_type = "ORB_MIDPOINT"
            inval_src_id = "orb_mid"

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-C-003",
                    category="BREAKOUT",
                    required_value=f"Price probing above OR High ({orb_high_val:.2f})",
                    observed_value=price,
                    passed=True,
                    severity=RuleSeverity.HARD,
                    detail=f"Bullish breakout setup established above OR High ({orb_high_val:.2f})",
                )
            )
        elif low_px < orb_low_val and extension_low_atr <= max_ext_atr and dir_score <= 20.0:
            eval_state = SignalState.ARMED
            reason_code = "SETUP_FORMED_WAITING_FOR_TRIGGER"
            pb_direction = "BEARISH"
            trigger_def = f"5m confirmed body close below OR Low ({orb_low_val:.2f})"
            trigger_px = float(orb_low_val)
            trig_src_type = "ORB_LOW_BOUNDARY"
            trig_src_id = "orb_low"
            inval_px = float(orb_mid)
            inval_src_type = "ORB_MIDPOINT"
            inval_src_id = "orb_mid"

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-C-003",
                    category="BREAKOUT",
                    required_value=f"Price probing below OR Low ({orb_low_val:.2f})",
                    observed_value=price,
                    passed=True,
                    severity=RuleSeverity.HARD,
                    detail=f"Bearish breakout setup established below OR Low ({orb_low_val:.2f})",
                )
            )
        elif orb_low_val <= price <= orb_high_val:
            eval_state = SignalState.WATCH
            reason_code = "WAITING_FOR_ORB_BREAKOUT"
            pb_direction = "BULLISH" if dir_score >= 0 else "BEARISH"
            trigger_def = f"Awaiting breakout beyond ORB boundary [{orb_low_val:.2f} - {orb_high_val:.2f}]"
            trigger_px = None
            trig_src_type = ""
            trig_src_id = ""
            inval_px = None
            inval_src_type = ""
            inval_src_id = ""

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-C-003",
                    category="BREAKOUT",
                    required_value="Price breakout beyond ORB boundary",
                    observed_value=price,
                    passed=False,
                    severity=RuleSeverity.SOFT,
                    detail=f"Price inside completed ORB range [{orb_low_val:.2f} - {orb_high_val:.2f}]",
                )
            )
        else:
            eval_state = SignalState.NO_SETUP
            reason_code = "SETUP_EXPIRED"
            pb_direction = "NEUTRAL"
            trigger_def = ""
            trigger_px = None
            trig_src_type = ""
            trig_src_id = ""
            inval_px = None
            inval_src_type = ""
            inval_src_id = ""

            rule_results.append(
                RuleResult(
                    rule_id="QX-PB-C-003",
                    category="BREAKOUT",
                    required_value=f"Price extension <= {max_ext_atr} ATR",
                    observed_value=price,
                    passed=False,
                    severity=RuleSeverity.HARD,
                    detail="Setup expired due to extreme extension beyond ORB boundary",
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
            trigger_knowledge_timestamp=ctx.knowledge_timestamp or ctx.event_timestamp,
            invalidation_price=inval_px,
            invalidation_source_type=inval_src_type,
            invalidation_source_id=inval_src_id,
            invalidation_knowledge_timestamp=ctx.knowledge_timestamp or ctx.event_timestamp,
            structural_target_candidates=target_candidates,
            publication_state=ctx.publication_state,
            direction_score=dir_score,
            direction_evidence_coverage=dir_cov,
            market_regime=ctx.market_regime,
            rule_results=rule_results,
            event_timestamp=ctx.event_timestamp,
            knowledge_timestamp=ctx.knowledge_timestamp,
            config_version=rules_cfg.version,
        )
