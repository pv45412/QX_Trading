from pydantic import BaseModel, Field


class BacktestParameters(BaseModel):
    profit_target_pct: float = Field(default=0.03, gt=0)
    stop_loss_pct: float = Field(default=0.03, gt=0)
    max_holding_bars: int = Field(default=20, ge=1)
    min_setup_score: float = Field(default=0.70, ge=0.0, le=1.0)
    entry_window_bars: int = Field(default=5, ge=1)
    require_breakout_trigger: bool = True
    fee_bps_per_side: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    slippage_bps_per_side: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    evaluation_fraction: float = Field(default=1, gt=0, le=1, allow_inf_nan=False)


class BacktestTrade(BaseModel):
    symbol: str
    signal_index: int
    entry_index: int
    entry_price: float
    exit_index: int
    exit_price: float
    outcome: str
    return_pct: float
    setup_score: float
    gross_return_pct: float | None = None


class BacktestResult(BaseModel):
    symbol: str
    trades: list[BacktestTrade]
    total_trades: int
    win_rate: float
    average_return_pct: float


class BacktestRunResult(BaseModel):
    results: list[BacktestResult]
    total_symbols: int
    total_trades: int
    win_rate: float
    average_return_pct: float
    failed_symbols: list[str] = Field(default_factory=list)
