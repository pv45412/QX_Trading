"""Trade Lifecycle Manager for Phase 3 Signal Quality & Validation.

Tracks full state machine transitions:
PROPOSED -> PENDING_ENTRY -> ACTIVE -> PARTIAL_TARGET -> STOPPED_OUT / TARGET_REACHED / EARLY_EXIT / EXPIRED.
Captures entry slippage, holding duration, and realized R-multiple outcomes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class LifecycleStage(str, Enum):
    PROPOSED = "PROPOSED"
    PENDING_ENTRY = "PENDING_ENTRY"
    ACTIVE = "ACTIVE"
    PARTIAL_TARGET = "PARTIAL_TARGET"
    STOPPED_OUT = "STOPPED_OUT"
    TARGET_REACHED = "TARGET_REACHED"
    EARLY_EXIT = "EARLY_EXIT"
    EXPIRED = "EXPIRED"


@dataclass
class LifecycleEvent:
    stage: LifecycleStage
    timestamp: datetime
    price: float
    notes: str = ""


@dataclass
class TradeLifecycleRecord:
    trade_id: str
    symbol: str
    direction: str  # BULLISH | BEARISH
    proposed_entry: float
    stop_loss: float
    target_1: float
    target_2: float
    current_stage: LifecycleStage = LifecycleStage.PROPOSED
    actual_entry_price: Optional[float] = None
    actual_exit_price: Optional[float] = None
    entry_slippage: float = 0.0
    realized_r_multiple: float = 0.0
    holding_hours: float = 0.0
    history: List[LifecycleEvent] = field(default_factory=list)

    def transition_to(
        self,
        new_stage: LifecycleStage,
        price: float,
        timestamp: Optional[datetime] = None,
        notes: str = "",
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc)
        self.current_stage = new_stage
        self.history.append(LifecycleEvent(stage=new_stage, timestamp=ts, price=price, notes=notes))

        if new_stage == LifecycleStage.ACTIVE and self.actual_entry_price is None:
            self.actual_entry_price = price
            self.entry_slippage = round(abs(price - self.proposed_entry), 4)

        if new_stage in (LifecycleStage.STOPPED_OUT, LifecycleStage.TARGET_REACHED, LifecycleStage.EARLY_EXIT, LifecycleStage.EXPIRED):
            self.actual_exit_price = price
            risk = abs(self.proposed_entry - self.stop_loss)
            if risk > 0 and self.actual_entry_price is not None:
                pnl = (price - self.actual_entry_price) if self.direction.upper() == "BULLISH" else (self.actual_entry_price - price)
                self.realized_r_multiple = round(pnl / risk, 2)

            if len(self.history) >= 2:
                entry_ts = self.history[0].timestamp
                if entry_ts.tzinfo is None:
                    entry_ts = entry_ts.replace(tzinfo=timezone.utc)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                self.holding_hours = round((ts - entry_ts).total_seconds() / 3600.0, 2)
