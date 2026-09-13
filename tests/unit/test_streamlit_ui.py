import pandas as pd
from types import SimpleNamespace

from qx.data.cache_status import CacheHealth
from qx.market.movers import market_movers_columns, market_movers_frame, scan_market_movers
from qx.models.market import BarDataRequest
from tests.unit.test_rectangle import _clean_rectangle_bars
from qx.patterns.rectangle import analyze_rectangle
from qx.patterns.profiles import build_rectangle_parameters
from qx.ui.app_shell import ensure_app_styles, page_slug, render_bullet_list, render_section_header
from qx.ui.pages import PAGES
from qx.ui.pages.command_center import (
    SAVED_SCANNER_NAMES,
    _same_command_universe,
    _snapshot_universe_label,
    _universe_id_for_command_mode,
    command_watchlist_options,
    _safe_display_frame,
)
from qx.ui.pages.data_cache import cache_action_items
from qx.ui.pages.heatmap import heatmap_candidates_frame
from qx.storage.options import StoredOptionIdea
from qx.ui.pages.daily_workflow import _options_watchlist_display_frame
from qx.ui.pages.morning_report import (
    _candidate_diagnostics_frame,
    _candidate_display_frame,
    _format_run_time,
)
from qx.ui.pages.performance import _options_performance_summary
from qx.ui.pages.pipeline import _pipeline_action_items
from qx.ui.pages.snapshot_history import _sector_focus_delta_frame, _sector_focus_frame
from qx.ui.pages.spx_dashboard import FUTURES_BOARD_SYMBOLS, _display_future_symbol, futures_timing_columns
from qx.ui.pages.ticker_history import build_history_frame, history_summary
from qx.ui.pages.schwab import _schwab_capability_rows
from qx.models.scan import ScanRunResult
from qx.ui.pages.scan import (
    SCAN_TYPE_GUIDE,
    SCAN_TYPE_OPTIONS,
    broad_breakout_lens_frame,
    filter_candidates,
    market_mover_display_frame,
    market_mover_sector_frame,
    ready_list_columns,
    ready_list_frame,
    scan_type_guide_markdown,
    scan_type_help,
    scanner_kpis,
    _selected_symbol_from_table_event,
)
from qx.ui.streamlit_app import (
    PAGE_GROUPS,
    PAGE_ROUTE_ALIASES,
    PAGE_ROUTE_TABS,
    _group_for_page,
    _module_selector,
    _page_from_current_path,
    _requested_tab_title,
    _pages_by_group,
    _workspace_pages,
)
from qx.ui.formatting import display_frame
from qx.ui.tables import (
    candidate_table,
    cast_existing_columns,
    rectangle_dashboard_columns,
    rectangle_detail_columns,
)
from qx.ui.status import cache_readiness_message, friendly_iso_time, log_size_label
from qx.data.metadata import SymbolMetadata
from qx.ui.metadata import displayed_candidate_metadata


class FakeStreamlit:
    def __init__(self) -> None:
        self.markdown_calls: list[tuple[str, bool]] = []

    def markdown(self, body: str, unsafe_allow_html: bool = False) -> None:
        self.markdown_calls.append((body, unsafe_allow_html))

    def caption(self, body: str) -> None:
        _ = body


class FakeMetadataStore:
    def __init__(self) -> None:
        self.enriched_symbols: list[str] = []

    def enrich_yfinance(self, symbols: list[str], *, max_symbols: int = 25) -> int:
        self.enriched_symbols = symbols[:max_symbols]
        return len(self.enriched_symbols)

    def get(self, symbol: str) -> SymbolMetadata:
        return SymbolMetadata(
            symbol=symbol,
            name=f"{symbol} Corp",
            sector="Industrials",
            industry="Engineering",
        )


class FakeMarketDataProvider:
    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        _ = request
        bars = _clean_rectangle_bars()
        bars.index = pd.bdate_range("2026-01-01", periods=len(bars))
        bars["high"] = bars[["open", "high", "close"]].max(axis=1)
        bars["low"] = bars[["open", "low", "close"]].min(axis=1)
        return bars


def test_app_styles_use_low_eye_strain_theme() -> None:
    fake = FakeStreamlit()

    ensure_app_styles(fake)

    css = "\n".join(body for body, _ in fake.markdown_calls)
    assert "--qx-accent: #3478ff" in css
    assert "--qx-sidebar-bg: #13181f" in css
    assert "--qx-bg: #0e1117" in css
    assert '[data-testid="stSidebarNav"]' in css
    assert '[data-testid="stToolbar"]' in css
    assert "stSegmentedControl" in css
    assert "#ff4b4b" not in css


def test_candidate_table_uses_current_score_columns() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())

    frame = candidate_table([candidate])

    assert "setup_score" in frame.columns
    assert "setup_status" in frame.columns
    assert "rank_score" in frame.columns
    assert "pattern_score" in frame.columns
    assert "readiness_score" in frame.columns
    assert "mtf_score" in frame.columns
    assert "weekly_status" in frame.columns
    assert "rule_score" in frame.columns
    assert "pattern_type" in frame.columns
    assert "directional_bias" in frame.columns
    assert "bias_ready_pct" in frame.columns
    assert "breakout_quality_label" in frame.columns
    assert "breakout_quality_pct" in frame.columns
    assert "target_label" in frame.columns
    assert "target_upside_pct" in frame.columns
    assert "timing_read" in frame.columns
    assert "trade_posture" in frame.columns
    assert "relative_volume_20d" in frame.columns
    assert "inside_close_pct" in frame.columns
    assert "breakout_level" in frame.columns
    assert "failure_level" in frame.columns
    assert "pivot_support_touches" in frame.columns
    assert "pivot_resistance_touches" in frame.columns
    assert not [column for column in rectangle_dashboard_columns() if column not in frame.columns]
    assert not [column for column in rectangle_detail_columns() if column not in frame.columns]


def test_candidate_table_uses_resolved_metadata() -> None:
    candidate = analyze_rectangle("AES", _clean_rectangle_bars())

    frame = candidate_table(
        [candidate],
        metadata_by_symbol={
            "AES": SymbolMetadata(
                symbol="AES",
                name="AES Corporation",
                sector="Utilities",
                industry="Independent Power Producers",
            )
        },
    )

    assert frame.loc[0, "sector"] == "Utilities"
    assert frame.loc[0, "industry"] == "Independent Power Producers"


def test_heatmap_frame_enriches_metadata_for_saved_candidates() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    metadata_store = FakeMetadataStore()

    frame = heatmap_candidates_frame(
        [candidate],
        metadata_store=metadata_store,  # type: ignore[arg-type]
        max_metadata_enrichment=10,
    )

    assert metadata_store.enriched_symbols == ["TEST"]
    assert frame.loc[0, "sector"] == "Industrials"
    assert frame.loc[0, "industry"] == "Engineering"


def test_displayed_candidate_metadata_enriches_visible_candidates() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    metadata_store = FakeMetadataStore()

    resolved, enriched = displayed_candidate_metadata(
        [candidate],
        metadata_store=metadata_store,  # type: ignore[arg-type]
        max_symbols=10,
    )

    assert resolved is metadata_store
    assert enriched == 1
    assert metadata_store.enriched_symbols == ["TEST"]


def test_scanner_display_frames_do_not_generate_duplicate_labels() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    table = candidate_table([candidate])

    frames = [
        display_frame(table, columns=rectangle_dashboard_columns()),
        display_frame(table, columns=rectangle_detail_columns()),
        display_frame(ready_list_frame(table), columns=ready_list_columns()),
    ]

    for frame in frames:
        labels = list(frame.columns)
        assert len(labels) == len(set(labels))


def test_cast_existing_columns_ignores_missing_columns() -> None:
    frame = pd.DataFrame({"setup_score": [0.75]})

    casted = cast_existing_columns(frame, {"score": "float64", "setup_score": "float64"})

    assert list(casted.columns) == ["setup_score"]
    assert str(casted["setup_score"].dtype) == "float64"


def test_filter_candidates_supports_strict_mode() -> None:
    passed = analyze_rectangle("PASS", _clean_rectangle_bars())
    rejected = passed.model_copy(update={"passed": False, "setup_score": 0.95})

    closest = filter_candidates([rejected, passed], min_score=0.70, strict_only=False, max_results=10)
    strict = filter_candidates([rejected, passed], min_score=0.70, strict_only=True, max_results=10)

    assert closest == [rejected, passed]
    assert strict == [passed]


def test_scanner_v2_ready_list_contract() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    table = candidate_table([candidate])

    ready = ready_list_frame(table)

    assert list(ready.columns) == ready_list_columns()
    assert ready.loc[0, "setup_type"] == "RectangleBreakout"
    assert ready.loc[0, "options_action"] in {"Review Contracts", "Watch Options", "Wait", "Avoid"}


def test_scanner_v2_ready_list_excludes_avoid_rows() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    table = candidate_table([candidate])
    table.loc[0, "qx_action"] = "Reject"
    table.loc[0, "trade_posture"] = "Avoid"

    ready = ready_list_frame(table)

    assert ready.empty
    assert list(ready.columns) == ready_list_columns()


def test_scanner_v2_selected_row_event_returns_symbol() -> None:
    frame = pd.DataFrame({"ticker": ["AAPL", "MSFT"]})

    assert _selected_symbol_from_table_event({"selection": {"rows": [1]}}, frame) == "MSFT"
    assert _selected_symbol_from_table_event(SimpleNamespace(selection=SimpleNamespace(rows=[0])), frame) == "AAPL"
    assert _selected_symbol_from_table_event({"selection": {"rows": [99]}}, frame) is None


def test_futures_timing_columns_show_execution_fields() -> None:
    columns = futures_timing_columns()

    assert columns[:3] == ["symbol", "name", "timing_state"]
    assert "trigger_level" in columns
    assert "invalidation_level" in columns
    assert "execution_note" in columns
    assert "risk_note" in columns


def test_futures_board_uses_major_contracts_and_display_labels() -> None:
    assert FUTURES_BOARD_SYMBOLS == [
        "ES=F",
        "NQ=F",
        "RTY=F",
        "YM=F",
        "CL=F",
        "GC=F",
        "ZN=F",
        "ZB=F",
        "DX-Y.NYB",
    ]
    assert _display_future_symbol("DX-Y.NYB") == "/DX"


def test_scanner_v2_broad_breakout_lens_contract() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    table = candidate_table([candidate])

    broad = broad_breakout_lens_frame(table)

    assert list(broad.columns) == [
        "ticker",
        "price",
        "sector",
        "pattern_type",
        "directional_bias",
        "bias_ready_pct",
        "breakout_quality_label",
        "breakout_quality_pct",
        "trend_status",
        "rs_status",
        "vol_status",
        "rvol",
        "breakout_status",
        "timing_read",
        "breakout_level",
        "distance_to_trigger_pct",
        "target_label",
        "target_upside_pct",
        "risk_reward",
        "qx_action",
        "trade_posture",
        "notes",
    ]
    assert broad.loc[0, "ticker"] == "TEST"
    assert isinstance(broad.loc[0, "notes"], str)


def test_scan_type_help_explains_each_lens() -> None:
    assert "support/resistance box" in scan_type_help("Rectangle")
    assert "Separate tape lens" in scan_type_help("Market Movers / Accumulation")
    assert "Broad Breakout" not in SCAN_TYPE_OPTIONS
    assert "Pullback Reclaim" not in SCAN_TYPE_OPTIONS


def test_scan_type_guide_markdown_covers_operational_lenses() -> None:
    guide = scan_type_guide_markdown()

    assert "Ready / Actionable" in guide
    assert "Market Movers / Accumulation" in guide
    assert "Replacing rectangle rules" in guide
    assert "Pullback Reclaim" not in guide


def test_scan_type_registry_keeps_options_help_and_guide_in_sync() -> None:
    guide = scan_type_guide_markdown()

    assert set(SCAN_TYPE_OPTIONS) == set(SCAN_TYPE_GUIDE)
    for scan_type in SCAN_TYPE_OPTIONS:
        assert scan_type in guide
        assert scan_type_help(scan_type) == SCAN_TYPE_GUIDE[scan_type]["help"]


def test_schwab_page_capability_rows_explain_provider_boundaries() -> None:
    rows = _schwab_capability_rows()

    assert any(row["Area"] == "Daily price history" and "Schwab primary" in row["Current Source"] for row in rows)
    assert any(row["Area"] == "Options chains" and row["Current Source"] == "Schwab primary" for row in rows)
    assert any(row["Area"] == "Fundamentals" and "fallback" in row["Current Source"] for row in rows)


def test_market_movers_lens_contract_is_separate_from_rectangle_scan() -> None:
    metadata_store = FakeMetadataStore()
    result = scan_market_movers(
        ["TEST"],
        FakeMarketDataProvider(),
        metadata_store=metadata_store,  # type: ignore[arg-type]
        limit=1,
    )

    frame = market_movers_frame(result.candidates)

    assert result.total_symbols == 1
    assert result.failed_symbols == 0
    assert metadata_store.enriched_symbols == []
    assert list(frame.columns)
    assert not [column for column in market_movers_columns() if column not in frame.columns]
    assert frame.loc[0, "symbol"] == "TEST"
    assert frame.loc[0, "sector"] == "Industrials"
    assert frame.loc[0, "dollar_volume"] > 0
    assert frame.loc[0, "rectangle_signal"] == "No rectangle signal"
    assert frame.loc[0, "mover_action"] in {
        "Review Now",
        "Rectangle Overlap",
        "Watch Tape",
        "Distribution Risk",
        "Monitor",
        "Liquidity Review",
    }


def test_market_movers_lens_can_annotate_rectangle_overlap_without_replacing_rules() -> None:
    rectangle = analyze_rectangle("TEST", _clean_rectangle_bars())
    result = scan_market_movers(
        ["TEST"],
        FakeMarketDataProvider(),
        metadata_store=FakeMetadataStore(),  # type: ignore[arg-type]
        rectangle_candidates=[rectangle],
        limit=1,
    )

    frame = market_movers_frame(result.candidates)

    assert frame.loc[0, "rectangle_signal"] == rectangle.setup_status
    assert frame.loc[0, "rectangle_score"] == round(rectangle.setup_score, 3)
    assert frame.loc[0, "notes"].endswith(f"rectangle {rectangle.setup_status}")
    assert "setup_score" not in frame.columns
    assert "missing_rules" not in frame.columns


def test_market_movers_dashboard_frames_are_decision_first() -> None:
    result = scan_market_movers(["TEST"], FakeMarketDataProvider(), metadata_store=FakeMetadataStore())  # type: ignore[arg-type]
    frame = market_movers_frame(result.candidates)

    display = market_mover_display_frame(frame)
    sector = market_mover_sector_frame(frame)

    assert "Action" in display.columns
    assert "Underlying Liquidity" in display.columns
    assert "Prior 20D Avg $ Vol" in display.columns
    assert "Mover Score" in display.columns
    assert "Sector" in sector.columns
    assert "Action" not in sector.columns


def test_scanner_v2_kpis_count_candidate_buckets() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    result = ScanRunResult(candidates=[candidate], total_symbols=1, passed_symbols=1)

    kpis = scanner_kpis(result, [candidate])

    assert kpis["total_scanned"] == 1
    assert kpis["rectangle_setups"] == 1
    assert kpis["average_qx_score"] > 0


def test_scanner_v2_kpis_count_broad_breakout_lens() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    candidate.metrics.trend_status = "Uptrend"
    candidate.metrics.rs_status = "Leader"
    candidate.metrics.relative_volume_20d = 1.25
    candidate.metrics.breakout_status = "Near Breakout"
    result = ScanRunResult(candidates=[candidate], total_symbols=1, passed_symbols=1)

    kpis = scanner_kpis(result, [candidate])

    assert kpis["broad_breakouts"] == 1


def test_classic_rectangle_profile_matches_user_rules() -> None:
    params = build_rectangle_parameters("Classic rectangle", lookback=50, max_range_pct=0.25)

    assert params.lookback == 50
    assert params.min_range_pct == 0.05
    assert params.max_range_pct == 0.25
    assert params.use_pivot_boundaries
    assert params.require_pivot_touches
    assert params.touch_tolerance_pct == 0.03
    assert params.pivot_order == 3
    assert params.require_flat_boundaries
    assert params.max_boundary_slope_pct == 0.03
    assert params.min_inside_close_pct == 0.80
    assert params.max_resistance_distance_pct == 0.05
    assert not params.require_volume_staircase
    assert not params.require_bullish_absorption
    assert not params.require_atr_compression
    assert not params.require_clean_recent_candles
    assert not params.require_prior_trend
    assert not params.require_base_above_50_sma


def test_page_registry_has_extendable_pages() -> None:
    assert [page.title for page in PAGES] == [
        "Scanner",
        "Daily Workflow",
        "Command Center",
        "Broad Watchlist",
        "Jobs",
        "Sector Rotation",
        "Run History",
        "SPX / NQ Futures",
        "Liquidity Map",
        "Options Ideas",
        "Ticker History",
        "Options Flow",
        "Idea Tracking",
        "Schwab API",
        "Strategy Rules",
        "Strategy Lab",
        "Data Cache",
        "Outcome Journal",
        "Morning Report",
        "Heatmap",
        "Backtest",
    ]


def test_page_navigation_is_grouped_for_clean_sidebar() -> None:
    grouped = _pages_by_group(PAGES)

    assert list(grouped) == list(PAGE_GROUPS)
    assert _group_for_page("Scanner") == "Scanner"
    assert _group_for_page("Options Ideas") == "Research"
    assert _group_for_page("Options Flow") == "Research"
    assert [page.title for page in grouped["Today"]] == [
        "Command Center",
        "Morning Report",
        "Daily Workflow",
    ]
    assert [page.title for page in _workspace_pages(PAGES)] == [
        "Today",
        "Scanner",
        "Markets",
        "Research",
        "Journal",
        "System",
    ]


def test_module_selector_prefers_segmented_control_when_available() -> None:
    class FakeStreamlitWithSegment:
        def segmented_control(self, *args: object, **kwargs: object) -> str:
            _ = args
            _ = kwargs
            return "Scanner"

    assert _module_selector(FakeStreamlitWithSegment(), ["Command Center", "Scanner"]) == "Scanner"


def test_module_selector_falls_back_to_horizontal_radio() -> None:
    class FakeStreamlitWithRadio:
        def radio(self, *args: object, **kwargs: object) -> str:
            assert kwargs["horizontal"] is True
            return "Backtest"

    assert _module_selector(FakeStreamlitWithRadio(), ["Scanner", "Backtest"]) == "Backtest"


def test_command_center_watchlist_universes_use_shared_registry() -> None:
    assert command_watchlist_options() == [
        SAVED_SCANNER_NAMES,
        "Dow Jones",
        "NASDAQ 100",
        "Russell 2000",
        "S&P 100",
        "S&P 500",
    ]
    assert _universe_id_for_command_mode("Russell 2000") == "russell_2000"
    assert _universe_id_for_command_mode(SAVED_SCANNER_NAMES) == "sp500"
    assert _snapshot_universe_label("NASDAQ 100") == "NASDAQ 100"
    assert _same_command_universe("sp500", "S&P 500")
    assert not _same_command_universe("sp500", "NASDAQ 100")


def test_page_slug_supports_clean_browser_paths() -> None:
    assert page_slug("Command Center") == "command_center"
    assert page_slug("Morning Report") == "morning_report"
    assert page_slug("SPX / NQ Futures") == "spx_nq_futures"


def test_page_route_aliases_support_file_style_urls() -> None:
    assert PAGE_ROUTE_ALIASES["spx_dashboard"] == "Markets"
    assert PAGE_ROUTE_ALIASES["liquidity_map"] == "Research"
    assert PAGE_ROUTE_ALIASES["options_flow"] == "Research"
    assert PAGE_ROUTE_ALIASES["pipeline"] == "System"
    assert PAGE_ROUTE_ALIASES["watchlist"] == "Scanner"


def test_ticker_history_aggregates_timeframes_and_reports_summary() -> None:
    index = pd.bdate_range("2026-01-01", periods=10)
    bars = pd.DataFrame(
        {
            "open": range(10, 20),
            "high": range(11, 21),
            "low": range(9, 19),
            "close": range(10, 20),
            "volume": [100.0] * 10,
        },
        index=index,
    )

    weekly = build_history_frame(bars, timeframe="Weekly")
    summary = history_summary(weekly)

    assert len(weekly) == 3
    assert summary["bars"] == 3
    assert summary["last"] == 19.0
    assert summary["period_return"] > 0
    assert summary["max_drawdown"] == 0.0


def test_page_from_current_path_prefers_route_alias() -> None:
    streamlit = type("FakeStreamlitContext", (), {"context": type("Context", (), {"url": "http://localhost/spx_dashboard"})()})()

    page = _page_from_current_path(streamlit, _workspace_pages(PAGES))

    assert page is not None
    assert page.title == "Markets"


def test_page_route_tabs_cover_internal_views() -> None:
    assert PAGE_ROUTE_TABS["spx_nq_futures"] == "SPX / NQ Futures"
    assert PAGE_ROUTE_TABS["command_snapshots"] == "Run History"
    assert PAGE_ROUTE_TABS["strategy_rules"] == "Strategy Rules"


def test_query_page_selects_internal_tab() -> None:
    streamlit = type(
        "FakeStreamlitContext",
        (),
        {"context": type("Context", (), {"url": "http://localhost/?page=spx_nq_futures"})()},
    )()

    assert _requested_tab_title(streamlit) == "SPX / NQ Futures"


def test_query_params_select_internal_tab_when_context_omits_query() -> None:
    streamlit = type(
        "FakeStreamlitQueryParams",
        (),
        {
            "context": type("Context", (), {"url": "http://localhost/"})(),
            "query_params": {"page": "command_snapshots"},
        },
    )()

    assert _requested_tab_title(streamlit) == "Run History"


def test_render_bullet_list_escapes_html_and_uses_shared_class() -> None:
    fake = FakeStreamlit()

    render_bullet_list(fake, ["Use prior high", "<script>alert(1)</script>"])

    body, unsafe = fake.markdown_calls[0]
    assert unsafe
    assert "qx-action-list" in body
    assert "Use prior high" in body
    assert "&lt;script&gt;" in body
    assert "<script>" not in body


def test_render_bullet_list_supports_empty_state() -> None:
    fake = FakeStreamlit()

    render_bullet_list(fake, [], empty="No action.")

    body, unsafe = fake.markdown_calls[0]
    assert unsafe
    assert "qx-empty" in body
    assert "No action." in body


def test_render_section_header_escapes_html_and_uses_shared_class() -> None:
    fake = FakeStreamlit()

    render_section_header(fake, "Market <Read>", "Wait for ES > prior high")

    body, unsafe = fake.markdown_calls[0]
    assert unsafe
    assert "qx-section-header" in body
    assert "Market &lt;Read&gt;" in body
    assert "ES &gt; prior high" in body
    assert "<Read>" not in body


def test_morning_report_display_frame_is_readable() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "quality": "Elite",
                "status": "Near Breakout",
                "sector": "Technology",
                "rank_score": 0.987,
                "setup_score": 0.91,
                "weekly_status": "Constructive Leader",
                "distance_to_resistance": 0.034,
                "range_pct": 0.12,
                "relative_volume_20d": 1.456,
                "missing": "",
            }
        ]
    )

    display = _candidate_display_frame(frame)

    assert list(display.columns) == [
        "Symbol",
        "Quality",
        "Status",
        "Sector",
        "Rank",
        "Setup",
        "Weekly",
        "To Resistance",
        "Range",
        "RVOL 20D",
    ]
    assert display.loc[0, "Rank"] == "0.99"
    assert display.loc[0, "To Resistance"] == "3.4%"
    assert display.loc[0, "RVOL 20D"] == "1.46x"


def test_morning_report_diagnostics_frame_keeps_rule_detail() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "sector": "Technology",
                "industry": "Software",
                "relative_volume_20d": 1.456,
                "missing": "",
            }
        ]
    )

    display = _candidate_diagnostics_frame(frame)

    assert list(display.columns) == ["Symbol", "Sector", "Industry", "RVOL 20D", "Missing Rules"]
    assert display.loc[0, "RVOL 20D"] == "1.46x"
    assert display.loc[0, "Missing Rules"] == "None"


def test_morning_report_formats_run_time() -> None:
    assert "2026" in _format_run_time("2026-06-01T06:46:01+00:00")


def test_command_center_snapshot_display_frame_handles_nested_payloads() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "rules": [{"name": "volume", "threshold": "> 0"}],
                "score": 0.85,
            }
        ]
    )

    display = _safe_display_frame(frame)

    assert isinstance(display.loc[0, "Rules"], str)
    assert "> 0" in display.loc[0, "Rules"]
    assert display.loc[0, "Score"] == "0.85"


def test_snapshot_history_sector_focus_frame_and_delta() -> None:
    current = {
        "sector_focus": [
            {"lens": "Leadership", "symbols": "Technology (XLK)", "read": "Leading"},
            {"lens": "Crowding Risk", "symbols": "Energy (XLE)", "read": "Extended"},
        ]
    }
    previous = {
        "sector_focus": [
            {"lens": "Leadership", "symbols": "Industrials (XLI)", "read": "Leading"},
            {"lens": "Crowding Risk", "symbols": "Energy (XLE)", "read": "Extended"},
        ]
    }

    frame = _sector_focus_frame(current)
    delta = _sector_focus_delta_frame(
        SimpleNamespace(
            current=SimpleNamespace(payload=current),
            previous=SimpleNamespace(payload=previous),
        )
    )

    assert list(frame.columns) == ["lens", "symbols", "read"]
    assert frame.loc[0, "lens"] == "Leadership"
    assert list(delta["lens"]) == ["Leadership"]
    assert delta.loc[0, "previous"] == "Industrials (XLI)"
    assert delta.loc[0, "current"] == "Technology (XLK)"


def test_command_center_cache_status_formatting_is_readable() -> None:
    health = CacheHealth(
        label="Ready",
        ready=True,
        coverage=1.0,
        latest_modified_at="2026-06-02T11:48:51+00:00",
        stale=False,
        message="Cache is broad and fresh enough for fast local scanning.",
    )

    assert "Jun 02, 2026" in friendly_iso_time(health.latest_modified_at)
    assert "Latest cache update" in cache_readiness_message(health)
    assert log_size_label(SimpleNamespace(exists=False, empty=True, size_bytes=0)) == "Missing"
    assert log_size_label(SimpleNamespace(exists=True, empty=True, size_bytes=0)) == "Empty"
    assert log_size_label(SimpleNamespace(exists=True, empty=False, size_bytes=1200)) == "1,200 bytes"


def test_data_cache_action_items_explain_next_operational_step() -> None:
    stale_health = CacheHealth(
        label="Stale",
        ready=False,
        coverage=0.80,
        latest_modified_at="2026-06-01T11:48:51+00:00",
        stale=True,
        message="Cache exists, but it is older than the freshness threshold.",
    )
    coverage = SimpleNamespace(period="2y", coverage=0.80, missing=100)
    pipeline = SimpleNamespace(
        cache_failures=0,
        scan_failures=0,
        auth_warning="",
    )

    actions = cache_action_items(health=stale_health, coverage=coverage, latest_pipeline=pipeline)

    assert any("forced cache refresh" in action for action in actions)
    assert any("clean enough" in action for action in actions)


def test_pipeline_action_items_explain_operational_next_step() -> None:
    auth_warning = SimpleNamespace(auth_warning="expired", cache_failures=0, scan_failures=0, candidates=10)
    data_issues = SimpleNamespace(auth_warning="", cache_failures=2, scan_failures=3, candidates=10)
    no_candidates = SimpleNamespace(auth_warning="", cache_failures=0, scan_failures=0, candidates=0)
    ready = SimpleNamespace(auth_warning="", cache_failures=0, scan_failures=0, candidates=5)

    assert any("Schwab API" in item for item in _pipeline_action_items(auth_warning))
    assert any("5 cache/scan failure" in item for item in _pipeline_action_items(data_issues))
    assert any("no candidates" in item for item in _pipeline_action_items(no_candidates))
    assert any("Command Center latest snapshot" in item for item in _pipeline_action_items(ready))


def test_display_frame_humanizes_common_trading_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "rank_score": 0.876,
                "range_pct": 0.124,
                "relative_volume_20d": 1.456,
                "missing": "",
                "payload": {"rule": "> 0"},
            }
        ]
    )

    display = display_frame(frame)

    assert list(display.columns) == ["Symbol", "Rank", "Range", "RVOL 20D", "Missing Rules"]
    assert display.loc[0, "Rank"] == "0.88"
    assert display.loc[0, "Range"] == "12.4%"
    assert display.loc[0, "RVOL 20D"] == "1.46x"
    assert display.loc[0, "Missing Rules"] == "None"


def test_display_frame_makes_duplicate_labels_unique() -> None:
    frame = pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "symbol": "TEST",
                "missing": "",
            }
        ]
    )

    display = display_frame(frame, columns=["ticker", "symbol", "missing", "missing"])

    assert list(display.columns) == ["Ticker", "Symbol", "Missing Rules", "Missing Rules 2"]


def test_display_frame_skips_missing_optional_columns() -> None:
    frame = pd.DataFrame({"symbol": ["AAPL"], "final_score": [0.82]})

    display = display_frame(
        frame,
        columns=[
            "symbol",
            "previous_saved_status",
            "previous_qx_action",
            "final_score",
        ],
    )

    assert list(display.columns) == ["Symbol", "Final"]


def test_display_frame_humanizes_options_performance_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "latest_underlying_price": 105.123,
                "latest_return_pct": 0.0523,
                "return_pct": -0.014,
            }
        ]
    )

    display = display_frame(frame)

    assert list(display.columns) == ["Symbol", "Latest Price", "Latest Return", "Return"]
    assert display.loc[0, "Latest Price"] == "105.12"
    assert display.loc[0, "Latest Return"] == "5.2%"
    assert display.loc[0, "Return"] == "-1.4%"


def test_daily_workflow_options_watchlist_uses_performance_columns() -> None:
    display = _options_watchlist_display_frame(
        [
            StoredOptionIdea(
                id=1,
                created_at="2026-06-03T11:00:00+00:00",
                symbol="TEST",
                action="Watch",
                direction="Bullish",
                strategy="Long Call",
                idea_score=0.81,
                status="Watch",
                entry_underlying_price=100.0,
                latest_underlying_price=105.25,
                latest_return_pct=0.0525,
                payload={},
            )
        ]
    )

    assert list(display.columns) == [
        "Symbol",
        "Status",
        "Direction",
        "Strategy",
        "Action",
        "Entry Price",
        "Latest Price",
        "Latest Return",
        "Idea Score",
        "Created",
    ]
    assert display.loc[0, "Entry Price"] == "100.00"
    assert display.loc[0, "Latest Price"] == "105.25"
    assert display.loc[0, "Latest Return"] == "5.2%"


def test_options_performance_summary_counts_saved_and_history() -> None:
    summary = _options_performance_summary(saved_count=4, history_count=7, tracked_count=2)

    assert summary == {
        "saved_ideas": 4,
        "performance_snapshots": 7,
        "tracked_ideas": 2,
    }
