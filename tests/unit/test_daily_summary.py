"""Unit test suite for Daily System Summary Report generator."""

from qx.reports.daily_summary import generate_daily_system_summary


def test_generate_daily_system_summary_empty():
    report = generate_daily_system_summary()
    assert report["system_status"] == "OPERATIONAL"
    assert "timestamp" in report
    assert report["summary"]["leading_sectors"] == []
    assert report["summary"]["options_ideas_count"] == 0


def test_generate_daily_system_summary_populated():
    etf_rows = [
        {"sector": "Technology", "rs_quadrant": "LEADING"},
        {"sector": "Financials", "rs_quadrant": "LAGGING"},
    ]
    options_ideas = [{"symbol": "NVDA"}, {"symbol": "AAPL"}]
    spx_data = {"spx_close": 5800.0, "gamma_flip": 5750.0}
    portfolio = {"total_equity": 250000.0, "publication_state": "VERIFIED"}

    report = generate_daily_system_summary(
        etf_rows=etf_rows,
        options_ideas=options_ideas,
        spx_data=spx_data,
        portfolio=portfolio,
    )

    assert report["summary"]["leading_sectors"] == ["Technology"]
    assert report["summary"]["lagging_sectors"] == ["Financials"]
    assert report["summary"]["options_ideas_count"] == 2
    assert report["summary"]["top_option_tickers"] == ["NVDA", "AAPL"]
    assert report["summary"]["spx_close"] == 5800.0
    assert report["summary"]["spx_gamma_flip"] == 5750.0
    assert report["summary"]["portfolio_equity"] == 250000.0
