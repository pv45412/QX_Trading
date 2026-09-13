"""RiskService for QX Options Scanner V1.

Implements strict account equity risk sizing rules:
Grade A+ (>=90): 0.75% - 1.00% risk
Grade A  (80-89.99): 0.50% - 0.75% risk
Grade B  (70-79.99): 0.25% - 0.50% risk
Below B (<70): No trade (0 contracts)

contracts = floor(allowed_risk / max_loss_per_contract)
"""

import math
from typing import Tuple, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from qx.options_scanner.config import ScannerConfig


class RiskSizingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    grade: str  # A+ | A | B | NO_TRADE
    overall_score: float
    account_equity: float
    risk_pct_applied: float
    allowed_risk_dollars: float
    max_loss_per_contract: float
    contracts_allowed: int
    is_trade_approved: bool


class RiskService:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def calculate_grade_and_risk(
        self,
        overall_score: float,
        account_equity: float,
        max_loss_per_contract: float
    ) -> RiskSizingResult:
        g = self.config.grades
        r = self.config.risk

        if overall_score >= g.a_plus:
            grade = "A+"
            risk_pct = r.a_plus_max_risk_pct
            approved = True
        elif overall_score >= g.a:
            grade = "A"
            risk_pct = r.a_max_risk_pct
            approved = True
        elif overall_score >= g.b:
            grade = "B"
            risk_pct = r.b_max_risk_pct
            approved = True
        else:
            grade = "NO_TRADE"
            risk_pct = 0.0
            approved = False

        allowed_risk_dollars = round(account_equity * risk_pct, 2)
        
        if not approved or max_loss_per_contract <= 0:
            contracts = 0
        else:
            contracts = math.floor(allowed_risk_dollars / max_loss_per_contract)

        return RiskSizingResult(
            grade=grade,
            overall_score=round(overall_score, 2),
            account_equity=round(account_equity, 2),
            risk_pct_applied=round(risk_pct, 4),
            allowed_risk_dollars=allowed_risk_dollars,
            max_loss_per_contract=round(max_loss_per_contract, 2),
            contracts_allowed=contracts,
            is_trade_approved=approved and contracts > 0
        )
