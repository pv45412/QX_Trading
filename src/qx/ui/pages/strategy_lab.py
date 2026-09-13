from typing import Any

import pandas as pd

from qx.backtesting.evaluation_protocol import (
    EvaluationProtocol,
    ReadOnlyEvaluationProvider,
    cached_evaluation_symbols,
    capture_evaluation_snapshot,
    evaluation_parameters,
)
from qx.backtesting.evaluation_report import evaluation_spec
from qx.backtesting.strategy_lab import STRATEGY_GRID, evaluate_strategy_snapshot
from qx.data.universe import UNIVERSE_OPTIONS
from qx.patterns.profiles import PROFILE_OPTIONS, build_rectangle_parameters, default_max_range_pct
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame
from qx.ui.pages.backtest import (
    EVALUATION_HISTORY_OPTIONS,
    _evaluation_cost_controls,
    _historical_evaluation_blocked,
    _matching_evaluation_report,
    _render_evaluation_report,
    _sync_evaluation_context,
)
from qx.ui.workspace_context import read_context


def render_strategy_lab_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    context = read_context(getattr(streamlit, "query_params", {}))
    universe_options = ["Custom", *UNIVERSE_OPTIONS]
    preferred = next((name for name, code in UNIVERSE_OPTIONS.items()
                      if code == context.get("universe")), "Custom")
    preferred_period = context.get("period", "2y")
    if preferred_period not in EVALUATION_HISTORY_OPTIONS:
        streamlit.warning(f"History {preferred_period} is unsupported for evaluation; selected 2y.")
        preferred_period = "2y"
    streamlit.subheader("Strategy Lab")
    streamlit.caption(
        "Exploratory training selection on cached daily bars. Final 25% of session dates reserved "
        "for one frozen candidate's holdout evaluation. No performance guarantees."
    )
    scope = streamlit.columns(2)
    universe_mode = scope[0].selectbox("Strategy lab universe", universe_options,
                                      index=universe_options.index(preferred), key="evaluation_lab_universe")
    symbols_text = scope[0].text_area("Strategy lab symbols", value=context.get("symbol", "AAPL\nMSFT\nNVDA"),
                                      disabled=universe_mode != "Custom", height=100, key="evaluation_lab_symbols")
    profile = scope[1].selectbox("Strategy profile", PROFILE_OPTIONS, index=1)
    period = scope[1].selectbox("Strategy history", EVALUATION_HISTORY_OPTIONS,
                                index=EVALUATION_HISTORY_OPTIONS.index(preferred_period), key="evaluation_lab_period")
    fee_bps, slippage_bps = _evaluation_cost_controls(streamlit, "strategy_lab")
    with streamlit.expander("Pattern and execution assumptions"):
        controls = streamlit.columns(2)
        lookback = controls[0].slider("Strategy pattern bars", 30, 60, 40, 5)
        max_range_pct = controls[1].slider(
            "Strategy max range %", 0.05, 0.25, default_max_range_pct(profile), 0.01)
        limit = controls[0].slider("Strategy symbol limit", 3, 100, 25, 1)
        profit_target = controls[1].slider("Strategy profit target %", 0.01, 0.20, 0.03, 0.01)
        stop_loss = controls[0].slider("Strategy stop loss %", 0.01, 0.20, 0.03, 0.01)
        max_holding = controls[1].slider("Strategy max holding bars", 5, 60, 20, 5)
    _sync_evaluation_context(streamlit, universe_mode, symbols_text, period)
    if _historical_evaluation_blocked(streamlit, "strategy_lab", "Run strategy comparison"):
        return
    try:
        requested = cached_evaluation_symbols(universe_mode, symbols_text)
    except (OSError, ValueError, KeyError):
        streamlit.error("Cached universe membership is unavailable or invalid.")
        return
    symbols = requested[:limit]
    streamlit.caption(f"Selected {len(symbols)} of {len(requested)} universe symbols (alphabetical limit).")
    spec = evaluation_spec(
        symbols, universe=universe_mode, period=period, profile=profile,
        scan_parameters=build_rectangle_parameters(profile, lookback=lookback, max_range_pct=max_range_pct),
        parameters=evaluation_parameters(fee_bps_per_side=fee_bps, slippage_bps_per_side=slippage_bps,
                                         profit_target_pct=profit_target, stop_loss_pct=stop_loss,
                                         max_holding_bars=max_holding),
        protocol=EvaluationProtocol(), kind="training_selection", grid=STRATEGY_GRID,
    )
    report = _matching_evaluation_report(streamlit, spec, "strategy_lab_report")
    if streamlit.button("Run strategy comparison", type="primary", icon=":material/play_arrow:", disabled=not symbols):
        with streamlit.spinner(f"Evaluating training grid for {len(symbols)} cached symbols..."):
            snapshot = capture_evaluation_snapshot(symbols, ReadOnlyEvaluationProvider(), period)
            report = evaluate_strategy_snapshot(spec, snapshot).report
        streamlit.session_state["strategy_lab_report"] = report
    if report is None:
        streamlit.info("No saved evaluation matches these settings and implementation.")
        return
    selected = report["selected_parameters"]
    if selected:
        streamlit.info(f"Training-selected candidate: setup score >= {selected['min_setup_score']}, "
                       f"{selected['entry_window_bars']} breakout bars. Not a production recommendation.")
    _render_evaluation_report(streamlit, report, "strategy_lab")
    streamlit.subheader("Training Comparison")
    streamlit.caption("Ranked only by mean net training trade return; holdout results excluded from ranking.")
    frame = pd.DataFrame(report["results"]["training_grid"]).drop(
        columns=["coverage", "warnings", "strategy_score"], errors="ignore")
    streamlit.dataframe(display_frame(frame), width="stretch", hide_index=True)
    streamlit.download_button(
        "Download strategy comparison CSV",
        frame.to_csv(index=False),
        file_name="strategy_lab.csv",
        mime="text/csv",
        icon=":material/download:",
        on_click="ignore",
    )


run_standalone_page(
    "Strategy Lab",
    "Compare scanner settings using historical breakout behavior.",
    render_strategy_lab_page,
)
