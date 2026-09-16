"""Phase 7: Entry Trigger & Confirmation Engine.

Evaluates previously ARMED PlaybookEvaluations against subsequent price action bars to detect
deterministic trigger events.

Enforces:
- ARMED -> TRIGGERED state transition
- Prohibition of EXECUTABLE state
- Causal temporal provenance (trigger_level_known_at <= armed_at < trigger_event_timestamp)
- Invalidation precedence ("INVALIDATION WINS")
- Bar close completion & precise BODY_CLOSE orientation
- Gap open metadata recording (actual observed price, no synthetic fills)
- Per-playbook configurable max_armed_bars lifetime expiration
- Terminal state immutability (TRIGGERED, SETUP_INVALIDATED, SETUP_EXPIRED)
- Source validity re-verification at trigger evaluation time
"""

from typing import Any, Dict, List, Optional, Set

from qx.config.rules_config import load_rules_config
from qx.models.rules import PublicationState, RuleResult, RuleSeverity, SignalState
from qx.playbooks.base import PlaybookEvaluation
from qx.triggers.models import TriggerEvent, TriggerRuleType, TriggeredSetupResult


class EntryTriggerEngine:
    """Engine for evaluating entry trigger and confirmation on previously ARMED setups."""

    def __init__(self, rules_config=None):
        self.rules_config = rules_config or load_rules_config()
        self.terminal_eval_ids: Set[str] = set()

    def evaluate_trigger(
        self,
        armed_eval: PlaybookEvaluation,
        bar: Dict[str, Any],
        bar_idx: int = 1,
        armed_bar_idx: int = 0,
        source_order_block: Optional[Dict[str, Any]] = None,
        source_fvg: Optional[Dict[str, Any]] = None,
        source_session_level_valid: bool = True,
        atr: float = 2.0,
    ) -> TriggeredSetupResult:
        """Evaluates an ARMED PlaybookEvaluation against a new completed bar context.

        Returns TriggeredSetupResult with state=TRIGGERED if trigger condition is met,
        or state=ARMED / NO_SETUP if not triggered / invalidated / expired.
        """
        eval_id = f"{armed_eval.playbook_id}_{armed_eval.event_timestamp}_{armed_eval.symbol}"

        # Rule 1: Terminal evaluation lifecycle check
        if eval_id in self.terminal_eval_ids:
            return TriggeredSetupResult(
                playbook_evaluation_id=eval_id,
                playbook_id=armed_eval.playbook_id,
                symbol=armed_eval.symbol,
                timeframe=armed_eval.timeframe,
                direction=armed_eval.direction,
                state=SignalState.NO_SETUP,
                trigger_event=None,
                armed_at=armed_eval.event_timestamp,
                trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                trigger_event_timestamp="",
                trigger_confirmed_at="",
                trigger_price=armed_eval.trigger_price or 0.0,
                invalidation_price=armed_eval.invalidation_price or 0.0,
                publication_state=armed_eval.publication_state,
                structure_valid=False,
                trigger_source_valid=False,
                evidence_ladder={"reason": "EVALUATION_IS_TERMINAL"},
            )

        # Rule 2: Publication state check
        if armed_eval.publication_state == PublicationState.BLOCKED:
            self.terminal_eval_ids.add(eval_id)
            return TriggeredSetupResult(
                playbook_evaluation_id=eval_id,
                playbook_id=armed_eval.playbook_id,
                symbol=armed_eval.symbol,
                timeframe=armed_eval.timeframe,
                direction=armed_eval.direction,
                state=SignalState.NO_SETUP,
                trigger_event=None,
                armed_at=armed_eval.event_timestamp,
                trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                trigger_event_timestamp="",
                trigger_confirmed_at="",
                trigger_price=armed_eval.trigger_price or 0.0,
                invalidation_price=armed_eval.invalidation_price or 0.0,
                publication_state=armed_eval.publication_state,
                structure_valid=False,
                trigger_source_valid=False,
                evidence_ladder={"reason": "BLOCKED_PUBLICATION_STATE"},
            )

        bar_open = float(bar.get("open", bar.get("close", 0.0)))
        bar_high = float(bar.get("high", bar.get("close", 0.0)))
        bar_low = float(bar.get("low", bar.get("close", 0.0)))
        bar_close = float(bar.get("close", 0.0))
        bar_time = str(bar.get("timestamp", bar.get("time", armed_eval.event_timestamp)))

        # Rule 3: Temporal causality check (must not arm and trigger on the same bar)
        if bar_time <= armed_eval.event_timestamp or bar_idx <= armed_bar_idx:
            return TriggeredSetupResult(
                playbook_evaluation_id=eval_id,
                playbook_id=armed_eval.playbook_id,
                symbol=armed_eval.symbol,
                timeframe=armed_eval.timeframe,
                direction=armed_eval.direction,
                state=SignalState.ARMED,
                trigger_event=None,
                armed_at=armed_eval.event_timestamp,
                trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                trigger_event_timestamp="",
                trigger_confirmed_at="",
                trigger_price=armed_eval.trigger_price or 0.0,
                invalidation_price=armed_eval.invalidation_price or 0.0,
                publication_state=armed_eval.publication_state,
                structure_valid=True,
                trigger_source_valid=True,
                evidence_ladder={"reason": "SAME_BAR_ARM_AND_TRIGGER_REJECTED"},
            )

        # Rule 4: Revalidate trigger source at trigger evaluation time
        if source_order_block is not None:
            ob_state = getattr(source_order_block, "state", None) or (source_order_block.get("state") if isinstance(source_order_block, dict) else "VALIDATED")
            ob_state_str = ob_state.value if hasattr(ob_state, "value") else str(ob_state)
            if ob_state_str in ("INVALIDATED", "EXPIRED"):
                self.terminal_eval_ids.add(eval_id)
                return TriggeredSetupResult(
                    playbook_evaluation_id=eval_id,
                    playbook_id=armed_eval.playbook_id,
                    symbol=armed_eval.symbol,
                    timeframe=armed_eval.timeframe,
                    direction=armed_eval.direction,
                    state=SignalState.NO_SETUP,
                    trigger_event=None,
                    armed_at=armed_eval.event_timestamp,
                    trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                    trigger_event_timestamp="",
                    trigger_confirmed_at="",
                    trigger_price=armed_eval.trigger_price or 0.0,
                    invalidation_price=armed_eval.invalidation_price or 0.0,
                    publication_state=armed_eval.publication_state,
                    structure_valid=False,
                    trigger_source_valid=False,
                    evidence_ladder={"reason": "SOURCE_INVALIDATED_AT_TRIGGER", "source_state": ob_state_str},
                )

        if not source_session_level_valid:
            self.terminal_eval_ids.add(eval_id)
            return TriggeredSetupResult(
                playbook_evaluation_id=eval_id,
                playbook_id=armed_eval.playbook_id,
                symbol=armed_eval.symbol,
                timeframe=armed_eval.timeframe,
                direction=armed_eval.direction,
                state=SignalState.NO_SETUP,
                trigger_event=None,
                armed_at=armed_eval.event_timestamp,
                trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                trigger_event_timestamp="",
                trigger_confirmed_at="",
                trigger_price=armed_eval.trigger_price or 0.0,
                invalidation_price=armed_eval.invalidation_price or 0.0,
                publication_state=armed_eval.publication_state,
                structure_valid=False,
                trigger_source_valid=False,
                evidence_ladder={"reason": "SOURCE_INVALIDATED_AT_TRIGGER"},
            )

        # Rule 5: Configurable armed setup expiration check
        trig_cfg = getattr(self.rules_config, "trigger_confirmation", None)
        max_armed_map = trig_cfg.max_armed_bars if trig_cfg else {}
        pb_map = max_armed_map.get(armed_eval.playbook_id, {}) if isinstance(max_armed_map, dict) else {}
        max_armed_bars = pb_map.get(armed_eval.timeframe, 12) if isinstance(pb_map, dict) else 12

        armed_age_bars = bar_idx - armed_bar_idx
        if armed_age_bars > max_armed_bars:
            self.terminal_eval_ids.add(eval_id)
            return TriggeredSetupResult(
                playbook_evaluation_id=eval_id,
                playbook_id=armed_eval.playbook_id,
                symbol=armed_eval.symbol,
                timeframe=armed_eval.timeframe,
                direction=armed_eval.direction,
                state=SignalState.NO_SETUP,
                trigger_event=None,
                armed_at=armed_eval.event_timestamp,
                trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                trigger_event_timestamp="",
                trigger_confirmed_at="",
                trigger_price=armed_eval.trigger_price or 0.0,
                invalidation_price=armed_eval.invalidation_price or 0.0,
                publication_state=armed_eval.publication_state,
                structure_valid=False,
                trigger_source_valid=False,
                evidence_ladder={"reason": "SETUP_EXPIRED", "armed_age_bars": armed_age_bars, "max_armed_bars": max_armed_bars},
            )

        is_bullish = armed_eval.direction == "BULLISH"
        inval_px = armed_eval.invalidation_price or 0.0
        trig_px = armed_eval.trigger_price or 0.0

        # Rule 6: Same-bar invalidation precedence ("INVALIDATION WINS")
        is_invalidated = (is_bullish and bar_low <= inval_px) or (not is_bullish and bar_high >= inval_px)
        if is_invalidated:
            self.terminal_eval_ids.add(eval_id)
            return TriggeredSetupResult(
                playbook_evaluation_id=eval_id,
                playbook_id=armed_eval.playbook_id,
                symbol=armed_eval.symbol,
                timeframe=armed_eval.timeframe,
                direction=armed_eval.direction,
                state=SignalState.NO_SETUP,
                trigger_event=None,
                armed_at=armed_eval.event_timestamp,
                trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                trigger_event_timestamp="",
                trigger_confirmed_at="",
                trigger_price=trig_px,
                invalidation_price=inval_px,
                publication_state=armed_eval.publication_state,
                structure_valid=False,
                trigger_source_valid=False,
                evidence_ladder={"reason": "SETUP_INVALIDATED", "invalidation_price": inval_px},
            )

        # Rule 7: Evaluate Trigger Condition
        rule_results: List[RuleResult] = []
        trigger_satisfied = False
        gap_triggered = False
        gap_distance = 0.0
        gap_distance_atr = 0.0

        # Check for gap open trigger
        gap_condition = (is_bullish and bar_open >= trig_px) or (not is_bullish and bar_open <= trig_px)

        if gap_condition:
            gap_triggered = True
            trigger_satisfied = True
            gap_distance = abs(bar_open - trig_px)
            gap_distance_atr = gap_distance / (atr if atr > 0 else 1.0)
            rule_type = TriggerRuleType.OPEN_GAP_ABOVE_LEVEL if is_bullish else TriggerRuleType.OPEN_GAP_BELOW_LEVEL
            rule_results.append(
                RuleResult(
                    rule_id="QX-TRIG-001",
                    category="TRIGGER_GAP",
                    required_value=f"Open gap beyond trigger price ({trig_px:.2f})",
                    observed_value=bar_open,
                    passed=True,
                    severity=RuleSeverity.HARD,
                    detail=f"Bar open ({bar_open:.2f}) gapped beyond trigger price ({trig_px:.2f}) by {gap_distance:.2f} ({gap_distance_atr:.2f} ATR)",
                )
            )
        else:
            # Bar close triggers for Playbooks A, B, C
            if armed_eval.playbook_id == "playbook_a_pullback":
                rule_type = TriggerRuleType.CLOSE_ABOVE_LEVEL if is_bullish else TriggerRuleType.CLOSE_BELOW_LEVEL
                trigger_satisfied = (is_bullish and bar_close >= trig_px) or (not is_bullish and bar_close <= trig_px)
            elif armed_eval.playbook_id == "playbook_b_liquidity_sweep":
                rule_type = TriggerRuleType.RECLAIM_ABOVE_LEVEL if is_bullish else TriggerRuleType.RECLAIM_BELOW_LEVEL
                trigger_satisfied = (is_bullish and bar_close >= trig_px) or (not is_bullish and bar_close <= trig_px)
            elif armed_eval.playbook_id == "playbook_c_orb_breakout":
                rule_type = TriggerRuleType.BODY_CLOSE_ABOVE_LEVEL if is_bullish else TriggerRuleType.BODY_CLOSE_BELOW_LEVEL
                # Precise BODY_CLOSE semantics:
                # Bullish: bar_close > trig_px AND bar_close > bar_open (bullish candle orientation)
                # Bearish: bar_close < trig_px AND bar_close < bar_open (bearish candle orientation)
                if is_bullish:
                    trigger_satisfied = (bar_close > trig_px) and (bar_close > bar_open)
                else:
                    trigger_satisfied = (bar_close < trig_px) and (bar_close < bar_open)

            rule_results.append(
                RuleResult(
                    rule_id="QX-TRIG-002",
                    category="TRIGGER_CLOSE",
                    required_value=f"5m bar close beyond trigger price ({trig_px:.2f})",
                    observed_value=bar_close,
                    passed=trigger_satisfied,
                    severity=RuleSeverity.HARD,
                    detail=f"Bar close ({bar_close:.2f}, open={bar_open:.2f}) trigger evaluation for {rule_type.value}",
                )
            )

        if not trigger_satisfied:
            # Setup remains ARMED awaiting future trigger
            return TriggeredSetupResult(
                playbook_evaluation_id=eval_id,
                playbook_id=armed_eval.playbook_id,
                symbol=armed_eval.symbol,
                timeframe=armed_eval.timeframe,
                direction=armed_eval.direction,
                state=SignalState.ARMED,
                trigger_event=None,
                armed_at=armed_eval.event_timestamp,
                trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
                trigger_event_timestamp="",
                trigger_confirmed_at="",
                trigger_price=trig_px,
                invalidation_price=inval_px,
                publication_state=armed_eval.publication_state,
                structure_valid=True,
                trigger_source_valid=True,
                evidence_ladder={"reason": "WAITING_FOR_TRIGGER"},
            )

        # Trigger Event Construction
        trig_event_id = f"trig_{armed_eval.symbol}_{bar_time.replace(':', '').replace('-', '')}"
        observed_px = bar_open if gap_triggered else bar_close
        trig_event = TriggerEvent(
            trigger_event_id=trig_event_id,
            playbook_id=armed_eval.playbook_id,
            playbook_version=armed_eval.playbook_version,
            symbol=armed_eval.symbol,
            timeframe=armed_eval.timeframe,
            direction=armed_eval.direction,
            trigger_source_type=armed_eval.trigger_source_type,
            trigger_source_id=armed_eval.trigger_source_id,
            trigger_price=trig_px,
            trigger_rule_type=rule_type,
            event_timestamp=bar_time,
            knowledge_timestamp=bar_time,
            confirmed_at=bar_time,
            observed_price=observed_px,
            bar_open=bar_open,
            bar_high=bar_high,
            bar_low=bar_low,
            bar_close=bar_close,
            confirmation_method="BAR_CLOSE_CONFIRMED" if not gap_triggered else "OPEN_GAP_CONFIRMED",
            gap_beyond_trigger=gap_triggered,
            gap_distance=gap_distance,
            gap_distance_atr=gap_distance_atr,
            publication_state=armed_eval.publication_state,
            source_playbook_evaluation_id=eval_id,
            rule_results=rule_results,
            config_version=armed_eval.config_version,
            engine_version="v7.0.0",
        )

        # Record terminal state for immutable lifecycle
        self.terminal_eval_ids.add(eval_id)

        return TriggeredSetupResult(
            playbook_evaluation_id=eval_id,
            playbook_id=armed_eval.playbook_id,
            symbol=armed_eval.symbol,
            timeframe=armed_eval.timeframe,
            direction=armed_eval.direction,
            state=SignalState.TRIGGERED,
            trigger_event=trig_event,
            armed_at=armed_eval.event_timestamp,
            trigger_level_known_at=armed_eval.trigger_knowledge_timestamp,
            trigger_event_timestamp=bar_time,
            trigger_confirmed_at=bar_time,
            trigger_price=trig_px,
            invalidation_price=inval_px,
            publication_state=armed_eval.publication_state,
            structure_valid=True,
            trigger_source_valid=True,
            evidence_ladder={
                "armed_score": armed_eval.direction_score,
                "trigger_rule_type": rule_type.value,
                "observed_price": observed_px,
                "gap_beyond_trigger": gap_triggered,
                "gap_distance": gap_distance,
                "gap_distance_atr": gap_distance_atr,
            },
            config_version=armed_eval.config_version,
            engine_version="v7.0.0",
            trade_state="NONE - TRADEABILITY NOT YET EVALUATED",
        )
