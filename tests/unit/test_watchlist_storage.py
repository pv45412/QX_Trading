from qx.storage.watchlist import SQLiteWatchlistRepository


def test_watchlist_repository_saves_symbols_and_updates_duplicates(tmp_path) -> None:
    repository = SQLiteWatchlistRepository(tmp_path / "qx.db")

    repository.add_symbol("aapl", source="qx", notes="first")
    repository.add_symbol("AAPL", source="rectangle_scanner", notes="updated")
    repository.add_symbol("MSFT", source="qx", notes="second")

    entries = repository.list_entries()
    symbols = repository.list_symbols()
    entries_by_symbol = {entry.symbol: entry for entry in entries}

    assert set(symbols) == {"AAPL", "MSFT"}
    assert len(entries) == 2
    assert entries_by_symbol["AAPL"].source == "rectangle_scanner"
    assert entries_by_symbol["AAPL"].notes == "updated"


def test_watchlist_repository_keeps_lists_separate(tmp_path) -> None:
    repository = SQLiteWatchlistRepository(tmp_path / "qx.db")

    repository.add_symbol("AAPL", list_name="scanner_review")
    repository.add_symbol("TSLA", list_name="options_review")

    assert repository.list_symbols(list_name="scanner_review") == ["AAPL"]
    assert repository.list_symbols(list_name="options_review") == ["TSLA"]


def test_watchlist_repository_preserves_saved_context_on_plain_update(tmp_path) -> None:
    repository = SQLiteWatchlistRepository(tmp_path / "qx.db")

    repository.add_symbol(
        "VRTX",
        source="rectangle_scanner",
        status="Watch",
        notes="initial context",
        context={
            "saved_status": "Near Breakout",
            "qx_action": "Watch",
            "trade_posture": "Review",
            "setup_score": 0.75,
        },
    )
    repository.add_symbol("VRTX", source="qx", notes="renamed note")

    entry = repository.list_entries()[0]

    assert entry.symbol == "VRTX"
    assert entry.source == "qx"
    assert entry.notes == "renamed note"
    assert entry.status == "Watch"
    assert entry.context["saved_status"] == "Near Breakout"
    assert entry.context["qx_action"] == "Watch"
