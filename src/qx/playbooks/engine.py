"""Phase 6: Playbook Engine Orchestrator.

Orchestrates evaluation across Playbook A (Pullback), Playbook B (Liquidity Sweep),
and Playbook C (ORB). Allows multiple playbooks to coexist without premature filtering.

Ranks primary_playbook_candidate deterministically (ARMED > WATCH > NO_SETUP).
Emits NO trade executions.
"""

from typing import Dict, List, Optional, Tuple

from qx.models.rules import SignalState
from qx.playbooks.base import BasePlaybookEvaluator, PlaybookEvaluation
from qx.playbooks.context import QXEvaluationContext
from qx.playbooks.liquidity_sweep import LiquiditySweepEvaluator
from qx.playbooks.orb import OpeningRangeBreakoutEvaluator
from qx.playbooks.pullback import TrendPullbackEvaluator


class PlaybookEngine:
    """Deterministic Engine for evaluating all QX Playbooks against context."""

    def __init__(self, evaluators: Optional[List[BasePlaybookEvaluator]] = None):
        if evaluators is None:
            self.evaluators: List[BasePlaybookEvaluator] = [
                TrendPullbackEvaluator(),
                LiquiditySweepEvaluator(),
                OpeningRangeBreakoutEvaluator(),
            ]
        else:
            self.evaluators = evaluators

    def evaluate_all(self, ctx: QXEvaluationContext) -> Tuple[List[PlaybookEvaluation], Optional[PlaybookEvaluation]]:
        """Evaluates all registered playbooks and returns (all_evaluations, primary_candidate)."""
        evaluations: List[PlaybookEvaluation] = []

        for evaluator in self.evaluators:
            eval_res = evaluator.evaluate(ctx)
            evaluations.append(eval_res)

        primary_candidate = self.select_primary_candidate(evaluations)
        return evaluations, primary_candidate

    @staticmethod
    def select_primary_candidate(evaluations: List[PlaybookEvaluation]) -> Optional[PlaybookEvaluation]:
        """Deterministically selects primary candidate based on state priority (ARMED > WATCH > NO_SETUP)

        and setup quality components. Does NOT discard alternate playbooks.
        """
        if not evaluations:
            return None

        # Filter active setups
        active = [e for e in evaluations if e.state in (SignalState.ARMED, SignalState.WATCH)]
        if not active:
            return evaluations[0]  # Return first NO_SETUP evaluation as default fallback

        # Priority score: ARMED = 200, WATCH = 100
        state_priority = {SignalState.ARMED: 200, SignalState.WATCH: 100, SignalState.NO_SETUP: 0}

        def rank_key(e: PlaybookEvaluation) -> float:
            base_prio = state_priority.get(e.state, 0)
            quality_bonus = sum(e.setup_quality_components.values()) / 10.0
            return base_prio + quality_bonus

        return max(active, key=rank_key)
