from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from qx.data.providers import MarketDataProvider
from qx.models.backtest import BacktestParameters, BacktestResult, BacktestRunResult, BacktestTrade
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.models.scan import RectangleScanParameters, ScanCandidate
from qx.patterns.rectangle import analyze_rectangle


def backtest_rectangle_breakouts(
    symbol: str,
    bars: pd.DataFrame,
    scan_parameters: RectangleScanParameters | None = None,
    backtest_parameters: BacktestParameters | None = None,
) -> BacktestResult:
    scan_params = scan_parameters or RectangleScanParameters()
    bt_params = backtest_parameters or BacktestParameters()
    trades: list[BacktestTrade] = []
    minimum_index = max(200, scan_params.lookback + 1, int(len(bars) * (1 - bt_params.evaluation_fraction)))
    last_exit_index = -1

    required_forward_bars = bt_params.entry_window_bars + bt_params.max_holding_bars
    for index in range(minimum_index, len(bars) - required_forward_bars):
        if index <= last_exit_index:
            continue

        history = bars.iloc[: index + 1]
        try:
            setup = analyze_rectangle(symbol, history, scan_params)
        except ValueError:
            continue
        if setup.setup_score < bt_params.min_setup_score:
            continue

        entry_index, entry_price = _entry_from_setup(bars, index, setup, bt_params)
        if entry_index is None or entry_price is None:
            continue

        target_price = entry_price * (1 + bt_params.profit_target_pct)
        stop_price = entry_price * (1 - bt_params.stop_loss_pct)
        future = bars.iloc[entry_index : entry_index + bt_params.max_holding_bars]
        exit_index = entry_index + len(future) - 1
        exit_price = float(future.iloc[-1]["close"])
        outcome = "timeout"

        for offset, (_, row) in enumerate(future.iterrows()):
            # Opening gaps take precedence only after the entry bar.
            if offset > 0 and float(row["open"]) <= stop_price:
                exit_index = entry_index + offset
                exit_price = float(row["open"])
                outcome = "loss"
                break
            if offset > 0 and float(row["open"]) >= target_price:
                exit_index = entry_index + offset
                exit_price = target_price
                outcome = "win"
                break
            if float(row["low"]) <= stop_price:
                exit_index = entry_index + offset
                exit_price = stop_price
                outcome = "loss"
                break
            if float(row["high"]) >= target_price:
                exit_index = entry_index + offset
                exit_price = target_price
                outcome = "win"
                break

        trades.append(
            BacktestTrade(
                symbol=symbol.upper(),
                signal_index=index,
                entry_index=entry_index,
                entry_price=entry_price,
                exit_index=exit_index,
                exit_price=exit_price,
                outcome=outcome,
                return_pct=net_trade_return(entry_price, exit_price, bt_params),
                gross_return_pct=(exit_price - entry_price) / entry_price,
                setup_score=setup.setup_score,
            )
        )
        last_exit_index = exit_index

    total = len(trades)
    wins = sum(trade.outcome == "win" for trade in trades)
    average_return = sum(trade.return_pct for trade in trades) / total if total else 0.0
    return BacktestResult(
        symbol=symbol.upper(),
        trades=trades,
        total_trades=total,
        win_rate=wins / total if total else 0.0,
        average_return_pct=average_return,
    )


def net_trade_return(entry: float, exit: float, parameters: BacktestParameters) -> float:
    fee = parameters.fee_bps_per_side / 10000
    slip = parameters.slippage_bps_per_side / 10000
    return exit * (1 - slip) * (1 - fee) / (entry * (1 + slip) * (1 + fee)) - 1


def _entry_from_setup(
    bars: pd.DataFrame,
    signal_index: int,
    setup: ScanCandidate,
    bt_params: BacktestParameters,
) -> tuple[int | None, float | None]:
    if not bt_params.require_breakout_trigger:
        entry_index = signal_index + 1
        return entry_index, float(bars.iloc[entry_index]["open"])

    breakout_level = setup.metrics.breakout_level
    entry_window = bars.iloc[signal_index + 1 : signal_index + 1 + bt_params.entry_window_bars]
    for offset, (_, row) in enumerate(entry_window.iterrows(), start=1):
        if float(row["high"]) >= breakout_level:
            return signal_index + offset, max(float(row["open"]), breakout_level)
    return None, None


def backtest_rectangle_universe(
    symbols: Iterable[str],
    provider: MarketDataProvider,
    *,
    period: str = "2y",
    scan_parameters: RectangleScanParameters | None = None,
    backtest_parameters: BacktestParameters | None = None,
    max_workers: int = 8,
) -> BacktestRunResult:
    results: list[BacktestResult] = []
    normalized_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    failed_symbols: list[str] = []

    def run_symbol(symbol: str) -> BacktestResult | None:
        try:
            bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
        except Exception:
            return None
        if bars.empty:
            return None
        return backtest_rectangle_breakouts(
            symbol,
            bars,
            scan_parameters=scan_parameters,
            backtest_parameters=backtest_parameters,
        )

    workers = max(1, min(max_workers, len(normalized_symbols) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_by_symbol = {executor.submit(run_symbol, symbol): symbol for symbol in normalized_symbols}
        for future in as_completed(future_by_symbol):
            result = future.result()
            if result is not None:
                results.append(result)
            else:
                failed_symbols.append(future_by_symbol[future])

    results.sort(key=lambda result: result.symbol)
    trades = [trade for result in results for trade in result.trades]
    wins = sum(trade.outcome == "win" for trade in trades)
    average_return = sum(trade.return_pct for trade in trades) / len(trades) if trades else 0.0
    return BacktestRunResult(
        results=results,
        total_symbols=len(normalized_symbols),
        total_trades=len(trades),
        win_rate=wins / len(trades) if trades else 0.0,
        average_return_pct=average_return,
        failed_symbols=sorted(failed_symbols),
    )


def sweep_backtest_parameters(
    symbols: Iterable[str],
    provider: MarketDataProvider,
    *,
    period: str = "2y",
    scan_parameters: RectangleScanParameters | None = None,
    setup_scores: Iterable[float] = (0.60, 0.70, 0.80),
    entry_windows: Iterable[int] = (3, 5, 10),
    profit_target_pct: float = 0.03,
    stop_loss_pct: float = 0.03,
    max_holding_bars: int = 20,
    max_workers: int = 8,
    fee_bps_per_side: float = 0,
    slippage_bps_per_side: float = 0,
) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    normalized_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    bars_by_symbol: dict[str, pd.DataFrame] = {}

    def load_symbol(symbol: str) -> tuple[str, pd.DataFrame] | None:
        try:
            return symbol, provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
        except Exception:
            return None

    workers = max(1, min(max_workers, len(normalized_symbols) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_by_symbol = {executor.submit(load_symbol, symbol): symbol for symbol in normalized_symbols}
        for future in as_completed(future_by_symbol):
            result = future.result()
            if result is not None:
                symbol, bars = result
                bars_by_symbol[symbol] = bars

    static_provider = _StaticBacktestProvider(bars_by_symbol)

    for min_setup_score in setup_scores:
        for entry_window_bars in entry_windows:
            run_result = backtest_rectangle_universe(
                bars_by_symbol.keys(),
                static_provider,
                period=period,
                scan_parameters=scan_parameters,
                backtest_parameters=BacktestParameters(
                    profit_target_pct=profit_target_pct,
                    stop_loss_pct=stop_loss_pct,
                    max_holding_bars=max_holding_bars,
                    min_setup_score=min_setup_score,
                    entry_window_bars=entry_window_bars,
                    require_breakout_trigger=True,
                    fee_bps_per_side=fee_bps_per_side,
                    slippage_bps_per_side=slippage_bps_per_side,
                ),
                max_workers=max_workers,
            )
            rows.append(
                {
                    "min_setup_score": round(min_setup_score, 2),
                    "entry_window_bars": entry_window_bars,
                    "symbols": run_result.total_symbols,
                    "trades": run_result.total_trades,
                    "win_rate": round(run_result.win_rate, 4),
                    "average_return_pct": round(run_result.average_return_pct, 4),
                }
            )
    return rows


class _StaticBacktestProvider:
    def __init__(self, bars_by_symbol: dict[str, pd.DataFrame]) -> None:
        self.bars_by_symbol = bars_by_symbol

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.bars_by_symbol[request.symbol.upper()]

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        raise NotImplementedError("Backtests use daily bars only")
