from typing import Any

import pandas as pd

from qx.backtesting.evaluation_protocol import (
    DEFAULT_FEE_BPS_PER_SIDE,
    DEFAULT_SLIPPAGE_BPS_PER_SIDE,
    EvaluationProtocol,
    ReadOnlyEvaluationProvider,
    cached_evaluation_symbols,
    capture_evaluation_snapshot,
    evaluation_parameters,
)
from qx.backtesting.evaluation_report import (
    content_hash,
    evaluate_fixed_snapshot,
    evaluation_spec,
    latest_compatible_report,
    report_json,
    save_evaluation_report,
)
from qx.data.universe import UNIVERSE_OPTIONS
from qx.models.backtest import BacktestRunResult
from qx.patterns.profiles import PROFILE_OPTIONS, build_rectangle_parameters, default_max_range_pct
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame
from qx.ui.workspace_context import read_context, sync_context, workspace_url

EVALUATION_HISTORY_OPTIONS = ["1y", "2y", "3y", "5y"]


def render_backtest_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    context = read_context(getattr(streamlit, "query_params", {}))
    universe_options = ["Custom", *UNIVERSE_OPTIONS]
    preferred = next((name for name, code in UNIVERSE_OPTIONS.items()
                      if code == context.get("universe")), "Custom")
    preferred_period = context.get("period", "2y")
    if preferred_period not in EVALUATION_HISTORY_OPTIONS:
        streamlit.warning(f"History {preferred_period} is unsupported for evaluation; selected 2y.")
        preferred_period = "2y"
    streamlit.subheader("Backtest")
    streamlit.caption(
        "Cached daily bars only. Fixed parameters; final 25% of session dates reserved for holdout. "
        "Earlier bars provide indicator warm-up. Historical simulation, no performance guarantees."
    )
    scope = streamlit.columns(2)
    universe_mode = scope[0].selectbox("Backtest universe", universe_options,
                                      index=universe_options.index(preferred), key="evaluation_bt_universe")
    symbols_text = scope[0].text_area("Backtest symbols", value=context.get("symbol", "AAPL\nMSFT\nNVDA"),
                                      disabled=universe_mode != "Custom", height=100, key="evaluation_bt_symbols")
    rule_profile = scope[1].selectbox("Backtest profile", PROFILE_OPTIONS, index=1)
    period = scope[1].selectbox("Backtest history", EVALUATION_HISTORY_OPTIONS,
                                index=EVALUATION_HISTORY_OPTIONS.index(preferred_period), key="evaluation_bt_period")
    fee_bps, slippage_bps = _evaluation_cost_controls(streamlit, "backtest")
    with streamlit.expander("Pattern and execution assumptions"):
        controls = streamlit.columns(2)
        lookback = controls[0].slider("Backtest pattern bars", 30, 60, 40, 5)
        max_range_pct = controls[1].slider(
            "Backtest max range %", 0.05, 0.25, default_max_range_pct(rule_profile), 0.01)
        profit_target_pct = controls[0].slider("Profit target %", 0.01, 0.20, 0.03, 0.01)
        stop_loss_pct = controls[1].slider("Stop loss %", 0.01, 0.20, 0.03, 0.01)
        max_holding_bars = controls[0].slider("Max holding bars", 5, 60, 20, 5)
        min_setup_score = controls[1].slider("Min setup score", 0.40, 0.95, 0.70, 0.05)
        entry_window_bars = controls[0].slider("Breakout window bars", 1, 20, 5, 1)
        require_breakout_trigger = controls[1].checkbox("Require breakout trigger", value=True)
    _sync_evaluation_context(streamlit, universe_mode, symbols_text, period)
    if _historical_evaluation_blocked(streamlit, "backtest", "Run backtest"):
        return
    params = build_rectangle_parameters(
        rule_profile, lookback=lookback, max_range_pct=max_range_pct,
    )
    bt_params = evaluation_parameters(
        profit_target_pct=profit_target_pct,
        stop_loss_pct=stop_loss_pct,
        max_holding_bars=max_holding_bars,
        min_setup_score=min_setup_score,
        entry_window_bars=entry_window_bars,
        require_breakout_trigger=require_breakout_trigger,
        fee_bps_per_side=fee_bps,
        slippage_bps_per_side=slippage_bps,
    )
    try:
        symbols = cached_evaluation_symbols(universe_mode, symbols_text)
    except (OSError, ValueError, KeyError):
        streamlit.error("Cached universe membership is unavailable or invalid.")
        return
    spec = evaluation_spec(symbols, universe=universe_mode, period=period, profile=rule_profile,
                           scan_parameters=params, parameters=bt_params, protocol=EvaluationProtocol())
    report = _matching_evaluation_report(streamlit, spec, "backtest_report")
    if streamlit.button("Run backtest", type="primary", icon=":material/play_arrow:", disabled=not symbols):
        with streamlit.spinner(f"Evaluating cached history for {len(symbols)} symbols..."):
            snapshot = capture_evaluation_snapshot(symbols, ReadOnlyEvaluationProvider(), period)
            report = evaluate_fixed_snapshot(spec, snapshot)
        streamlit.session_state["backtest_report"] = report
    if report is None:
        streamlit.info("No saved evaluation matches these settings and implementation.")
        return
    _render_evaluation_report(streamlit, report, "backtest")


def _sync_evaluation_context(streamlit: Any, universe: str, symbols_text: str, period: str) -> None:
    updates = {"universe": UNIVERSE_OPTIONS.get(universe, "custom"), "period": period}
    symbols = [symbol.strip().upper() for symbol in symbols_text.replace(",", "\n").splitlines() if symbol.strip()]
    if universe == "Custom" and len(set(symbols)) == 1:
        updates["symbol"] = symbols[0]
    sync_context(streamlit, **updates)


def _historical_evaluation_blocked(streamlit: Any, route: str, label: str) -> bool:
    query = getattr(streamlit, "query_params", {})
    context = read_context(query)
    if not query.get("as_of") and not query.get("snapshot"):
        return False
    streamlit.button(label, type="primary", icon=":material/play_arrow:", disabled=True)
    requested = context.get("as_of") or (
        f"snapshot {context['snapshot']}" if context.get("snapshot") else "invalid date or snapshot")
    streamlit.warning(f"Requested evidence: {requested}. This evaluation does not replay historical "
                      "workspace selections; current cached data was not evaluated.")
    streamlit.link_button("Use current evidence", workspace_url(route, context, as_of="", snapshot=""))
    return True


def _evaluation_cost_controls(streamlit: Any, key: str) -> tuple[float, float]:
    columns = streamlit.columns(2)
    fee = columns[0].number_input("Fees per side (bps)", min_value=0.0, max_value=1000.0,
                                  value=DEFAULT_FEE_BPS_PER_SIDE, key=f"{key}_fees")
    slip = columns[1].number_input("Slippage per side (bps)", min_value=0.0, max_value=1000.0,
                                   value=DEFAULT_SLIPPAGE_BPS_PER_SIDE, key=f"{key}_slippage")
    return float(fee), float(slip)


def _matching_evaluation_report(streamlit: Any, spec: dict[str, Any], key: str) -> dict[str, Any] | None:
    report: dict[str, Any] | None = streamlit.session_state.get(key)
    if report is not None and report.get("spec") == spec:
        return report
    fingerprint = content_hash(spec)
    if streamlit.session_state.get(f"{key}_lookup") != fingerprint:
        report = latest_compatible_report(spec)
        streamlit.session_state[key] = report
        streamlit.session_state[f"{key}_lookup"] = fingerprint
        return report
    return None


def _render_evaluation_report(streamlit: Any, report: dict[str, Any], key: str) -> None:
    records = report["data"]["symbols"]
    asofs = sorted({row["asof"] for row in records if row["status"] == "captured"})
    streamlit.subheader("Historical Evaluation")
    streamlit.caption(f"Report {report['report_id'][:12]} | Created {report['generated_at']} | "
                      f"Holdout starts {report['split']['holdout_start'] or 'unavailable'}")
    if asofs:
        streamlit.caption(f"Symbol data through {asofs[0]} to {asofs[-1]}; current cache not revalidated.")
    costs = report["spec"]["costs"]
    streamlit.caption(f"Per-side fees {costs['fee_bps_per_side']:g} bps; "
                      f"slippage {costs['slippage_bps_per_side']:g} bps. Returns are net per trade.")
    streamlit.warning("Exploratory historical evidence, not a validated edge. No performance guarantees. "
                      "Retuning after viewing holdout results contaminates the holdout.")
    heldout = report["results"]["holdout"]
    if heldout is None:
        streamlit.info("Holdout not evaluated: no candidate with usable training trades.")
    else:
        for warning in heldout["warnings"]:
            streamlit.warning(warning)
        _render_backtest_result(streamlit, BacktestRunResult.model_validate(heldout["result"]))
    training = report["results"]["training"]
    if training:
        for warning in training["warnings"]:
            streamlit.warning(warning)
    with streamlit.expander("Evidence, coverage and limitations"):
        for warning in report["warnings"]:
            streamlit.caption(warning)
        for phase in ("training", "holdout"):
            result = report["results"][phase]
            if result:
                streamlit.caption(f"{phase.title()} coverage")
                streamlit.dataframe(pd.DataFrame(result["coverage"]), width="stretch", hide_index=True)
        streamlit.json({"spec": report["spec"], "split": report["split"],
                        "selected_parameters": report["selected_parameters"],
                        "data_sha256": report["data"]["sha256"]})
    actions = streamlit.columns(2)
    actions[0].download_button("Export evaluation JSON", report_json(report),
                               file_name=f"evaluation_{report['report_id'][:12]}.json",
                               mime="application/json", icon=":material/download:",
                               key=f"{key}_export", on_click="ignore")
    if actions[1].button("Save evaluation report", icon=":material/save:", key=f"{key}_save"):
        try:
            path = save_evaluation_report(report)
            streamlit.success(f"Saved {path.name}")
        except (OSError, ValueError, KeyError, TypeError):
            streamlit.error("Report could not be saved. No evaluation was rerun.")


def _render_backtest_result(streamlit: Any, result: BacktestRunResult) -> None:
    streamlit.subheader("Backtest Summary")
    streamlit.caption(f"Evaluated {len(result.results)} of {result.total_symbols} requested symbols")
    if result.failed_symbols:
        streamlit.warning("Incomplete data coverage. Unavailable symbols: " + ", ".join(result.failed_symbols))
    analytics = backtest_analytics(result)
    metric_columns = streamlit.columns(3)
    metric_columns[0].metric("Evaluated symbols", len(result.results))
    metric_columns[1].metric("Trades", result.total_trades)
    metric_columns[2].metric("Avg Net Return", f"{result.average_return_pct:.2%}" if result.total_trades else "N/A")
    secondary = streamlit.columns(3)
    secondary[0].metric("Target-hit Rate", f"{result.win_rate:.1%}" if result.total_trades else "N/A")
    secondary[1].metric("Expectancy", f"{analytics['expectancy_pct']:.2%}" if result.total_trades else "N/A")
    secondary[2].metric("Profit Factor", _profit_factor_text(analytics["profit_factor"]) if result.total_trades else "N/A")

    summary = backtest_summary_frame(result)
    tabs = streamlit.tabs(["Analytics", "Symbols", "Trades"])
    with tabs[0]:
        streamlit.dataframe(display_frame(backtest_analytics_frame(result)), width="stretch", hide_index=True)
        streamlit.dataframe(display_frame(backtest_outcome_frame(result)), width="stretch", hide_index=True)
    with tabs[1]:
        streamlit.dataframe(display_frame(summary), width="stretch", hide_index=True)
    with tabs[2]:
        trades = backtest_trades_frame(result)
        if trades.empty:
            streamlit.info("No trade rows to display.")
        else:
            streamlit.dataframe(display_frame(trades), width="stretch", hide_index=True)
    if not result.results:
        streamlit.error("No symbols were evaluated. Check data availability before interpreting this run.")
    elif result.total_trades == 0:
        streamlit.info(
            "No historical trades matched these settings. This is not evidence of profitability. "
            "Do not tune parameters to this holdout."
        )
    streamlit.download_button(
        "Download backtest summary CSV",
        summary.to_csv(index=False),
        file_name="backtest_summary.csv",
        mime="text/csv",
        icon=":material/download:",
        on_click="ignore",
    )


def backtest_analytics(result: BacktestRunResult) -> dict[str, float | int]:
    trades = [trade for item in result.results for trade in item.trades]
    returns = [float(trade.return_pct) for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    timeouts = [trade for trade in trades if trade.outcome == "timeout"]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    average_win = sum(wins) / len(wins) if wins else 0.0
    average_loss = sum(losses) / len(losses) if losses else 0.0
    profit_probability = len(wins) / len(trades) if trades else 0.0
    expectancy = profit_probability * average_win + (1 - profit_probability) * average_loss if trades else 0.0
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "average_win_pct": average_win,
        "average_loss_pct": average_loss,
        "expectancy_pct": expectancy,
        "best_trade_pct": max(returns) if returns else 0.0,
        "worst_trade_pct": min(returns) if returns else 0.0,
        "profit_factor": profit_factor,
    }


def backtest_analytics_frame(result: BacktestRunResult) -> pd.DataFrame:
    analytics = backtest_analytics(result)
    return pd.DataFrame(
        [
            {"metric": "Trades", "value": analytics["trades"]},
            {"metric": "Wins", "value": analytics["wins"]},
            {"metric": "Losses", "value": analytics["losses"]},
            {"metric": "Timeouts", "value": analytics["timeouts"]},
            {"metric": "Average Win", "value": round(float(analytics["average_win_pct"]), 4)},
            {"metric": "Average Loss", "value": round(float(analytics["average_loss_pct"]), 4)},
            {"metric": "Expectancy", "value": round(float(analytics["expectancy_pct"]), 4)},
            {"metric": "Best Trade", "value": round(float(analytics["best_trade_pct"]), 4)},
            {"metric": "Worst Trade", "value": round(float(analytics["worst_trade_pct"]), 4)},
            {"metric": "Profit Factor", "value": round(float(analytics["profit_factor"]), 3)},
        ]
    )


def backtest_outcome_frame(result: BacktestRunResult) -> pd.DataFrame:
    trades = [trade for item in result.results for trade in item.trades]
    if not trades:
        return pd.DataFrame(columns=["outcome", "trades", "average_return_pct"])
    frame = pd.DataFrame([trade.model_dump() for trade in trades])
    return (
        frame.groupby("outcome", dropna=False)
        .agg(
            trades=("symbol", "count"),
            average_return_pct=("return_pct", "mean"),
            average_setup_score=("setup_score", "mean"),
        )
        .reset_index()
        .sort_values("trades", ascending=False)
        .round(4)
    )


def backtest_trades_frame(result: BacktestRunResult) -> pd.DataFrame:
    trades = [trade.model_dump() for item in result.results for trade in item.trades]
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame(trades).sort_values(["symbol", "signal_index"]).reset_index(drop=True)


def backtest_summary_frame(result: BacktestRunResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": item.symbol,
                "trades": item.total_trades,
                "win_rate": round(item.win_rate, 4),
                "average_return_pct": round(item.average_return_pct, 4),
            }
            for item in result.results
        ]
    )


def _profit_factor_text(value: float | int) -> str:
    if value == float("inf"):
        return "No losses"
    return f"{float(value):.2f}"


run_standalone_page(
    "Backtest",
    "Measure historical scanner signal behavior before trusting a setup.",
    render_backtest_page,
)
