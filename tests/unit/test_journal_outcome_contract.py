from contextlib import closing
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
import sqlite3

import pytest

from qx.storage.journal import JournalEntry, SQLiteJournalRepository
from qx.ui.pages import journal


def closed_entry(**updates: object) -> JournalEntry:
    fields = {
        "record_type": "paper", "symbol": "TEST", "instrument": "equity", "side": "long",
        "decision_date": date(2026, 1, 1), "entry_date": date(2026, 1, 2),
        "exit_date": date(2026, 1, 3), "entry_price": Decimal("100.10"),
        "exit_price": Decimal("105.20"), "quantity": Decimal("3"),
        "multiplier": Decimal("1"), "fees": Decimal("1.01"),
        "thesis": "Test thesis", "evidence_ref": "scan:123", "planned_invalidation": "Test rule",
    }
    return JournalEntry(**(fields | updates))


def research_entry() -> JournalEntry:
    return JournalEntry(
        record_type="research", symbol="TEST", instrument="equity", side="long",
        decision_date=date(2026, 1, 1), thesis="A hypothesis, not an execution",
        evidence_ref="snapshot:5", planned_invalidation="Test rule",
    )


@pytest.mark.parametrize(("updates", "expected"), [
    ({}, "14.29"),
    ({"side": "short"}, "-16.31"),
    ({"side": "short", "entry_price": Decimal("105.20"),
      "exit_price": Decimal("100.10")}, "14.29"),
    ({"exit_price": Decimal("100.10")}, "-1.01"),
    ({"entry_price": Decimal("0.1"), "exit_price": Decimal("0.2"),
      "quantity": Decimal("3"), "fees": Decimal("0.1")}, "0.20"),
    ({"entry_price": Decimal("1"), "exit_price": Decimal("1.01"),
      "quantity": Decimal("0.5"), "fees": Decimal("0")}, "0.01"),
    ({"entry_price": Decimal("1.01"), "exit_price": Decimal("1"),
      "quantity": Decimal("0.5"), "fees": Decimal("0")}, "-0.01"),
])
def test_closed_equity_net_pnl(updates: dict[str, object], expected: str) -> None:
    with localcontext() as context:
        context.prec = 6
        entry = closed_entry(**updates)
        assert entry.net_pnl == Decimal(expected)
    assert entry.status == "closed"


@pytest.mark.parametrize("field", ["entry_price", "exit_price", "quantity", "multiplier"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "0", "-1", "", None, True,
                                   "0.000000001", "1000000000001"])
def test_positive_finite_amount_validation(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        closed_entry(**{field: value})


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "", None, "0.000000001"])
def test_nonnegative_finite_fees(value: object) -> None:
    with pytest.raises(ValueError):
        closed_entry(fees=value)


@pytest.mark.parametrize("updates", [
    {"instrument": "option", "multiplier": Decimal("100")},
    {"instrument": "future", "multiplier": Decimal("50")},
    {"multiplier": Decimal("100")}, {"currency": "EUR"}, {"side": "buy"},
    {"record_type": "signal"}, {"symbol": ""}, {"symbol": "SPX 5000 CALL"},
    {"thesis": ""}, {"evidence_ref": " "}, {"planned_invalidation": ""},
    {"entry_date": None}, {"exit_date": None}, {"exit_date": date(2026, 1, 1)},
    {"decision_date": date(2026, 1, 3)}, {"exit_date": date.today() + timedelta(days=1)},
    {"entry_date": "2026-01-02T10:00:00Z"}, {"exit_date": "20260103"},
    {"exit_price": None}, {"quantity": None},
])
def test_unsupported_or_incomplete_outcomes_are_rejected(updates: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        closed_entry(**updates)


def test_research_is_not_a_trade() -> None:
    research = research_entry()
    assert research.status == "research"
    assert research.net_pnl is None
    for updates in ({"entry_price": Decimal("100")}, {"quantity": Decimal("1")},
                    {"fees": Decimal("1")}, {"exit_date": date(2026, 1, 3)}):
        with pytest.raises(ValueError):
            replace(research, **updates)


def test_reading_empty_repository_never_creates_db_or_directory(tmp_path: Path) -> None:
    path = tmp_path / "not-created" / "journal.db"
    repository = SQLiteJournalRepository(path)
    assert repository.list_entries(record_type="paper") == []
    assert repository.count_entries(record_type="research") == 0
    assert not path.parent.exists()


def test_table_is_independent_and_reading_existing_db_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "journal.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE scanner_signals (id INTEGER)")
        connection.execute("INSERT INTO scanner_signals VALUES (7)")
        connection.commit()
    original = path.read_bytes()
    repository = SQLiteJournalRepository(path)
    assert repository.list_entries(record_type="live") == []
    assert path.read_bytes() == original
    repository.save(closed_entry())
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT * FROM scanner_signals").fetchall() == [(7,)]
        row = connection.execute(
            "SELECT net_pnl, typeof(net_pnl), calculation_version FROM journal_entries"
        ).fetchone()
    assert row == ("14.29", "text", "closed_equity_v1")


def test_persisted_modes_and_pagination_are_separate(tmp_path: Path) -> None:
    repository = SQLiteJournalRepository(tmp_path / "journal.db")
    first_id = repository.save(closed_entry(symbol=" test "))
    second_id = repository.save(closed_entry())
    repository.save(closed_entry(record_type="live"))
    repository.save(research_entry())
    assert repository.count_entries(record_type="paper") == 2
    assert repository.count_entries(record_type="live") == 1
    assert repository.count_entries(record_type="research") == 1
    assert repository.list_entries(record_type="paper", limit=1)[0].id == second_id
    stored = repository.list_entries(record_type="paper", limit=1, offset=1)[0]
    assert stored.id == first_id
    assert stored.entry.symbol == "TEST"
    assert stored.entry.net_pnl == Decimal("14.29")
    assert stored.entry.entry_date == date(2026, 1, 2)
    assert stored.created_at.endswith("+00:00")
    assert repository.list_entries(record_type="research")[0].entry.net_pnl is None
    assert "Net Closed P&L USD" not in journal.journal_entries_frame(
        repository.list_entries(record_type="research")
    ).columns


def test_same_submission_is_idempotent_and_conflicts_are_rejected(tmp_path: Path) -> None:
    repository = SQLiteJournalRepository(tmp_path / "journal.db")
    saved_id = repository.save(closed_entry(), submission_id="explicit-save-1")
    same = closed_entry(entry_price=Decimal("100.1000"), quantity=Decimal("3.0"))
    assert repository.save(same, submission_id="explicit-save-1") == saved_id
    with pytest.raises(ValueError, match="different record"):
        repository.save(closed_entry(quantity=Decimal("4")), submission_id="explicit-save-1")
    assert repository.count_entries(record_type="paper") == 1


def test_invalid_save_does_not_create_database(tmp_path: Path) -> None:
    path = tmp_path / "invalid.db"
    entry = closed_entry()
    object.__setattr__(entry, "exit_price", Decimal("NaN"))
    with pytest.raises(ValueError):
        SQLiteJournalRepository(path).save(entry)
    assert not path.exists()


def test_corrupted_pnl_is_not_silently_displayed(tmp_path: Path) -> None:
    path = tmp_path / "journal.db"
    repository = SQLiteJournalRepository(path)
    repository.save(closed_entry())
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("UPDATE journal_entries SET net_pnl = '999.99'")
        connection.commit()
    with pytest.raises(ValueError, match="integrity"):
        repository.list_entries(record_type="paper")


class JournalFormUI:
    def __init__(self, *, submitted: bool = False, confirmed: bool = True) -> None:
        self.submitted = submitted
        self.confirmed = confirmed
        self.session_state: dict[str, object] = {}
        self.query_params = {"symbol": "TEST", "snapshot": "5"}
        self.errors: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def form(self, *args, **kwargs):
        return self

    def columns(self, number):
        return [self] * number

    def text_input(self, label, **kwargs):
        return {"Entry price (USD / share)": "100", "Exit price (USD / share)": "105",
                "Quantity (shares)": "2"}.get(label, kwargs.get("value", "evidence"))

    def selectbox(self, label, options, **kwargs):
        return options[0]

    def date_input(self, *args, **kwargs):
        return date(2026, 1, 1)

    def text_area(self, *args, **kwargs):
        return "User-entered text"

    def number_input(self, *args, **kwargs):
        return kwargs["value"]

    def caption(self, *args):
        pass

    def checkbox(self, *args):
        return self.confirmed

    def form_submit_button(self, *args, **kwargs):
        return self.submitted

    def error(self, message):
        self.errors.append(message)

    def success(self, *args):
        pass


def test_form_writes_only_on_confirmed_explicit_save(tmp_path: Path) -> None:
    path = tmp_path / "journal.db"
    repository = SQLiteJournalRepository(path)
    ui = JournalFormUI()
    journal._render_entry_form(ui, repository, "paper")
    assert not path.exists()
    ui.submitted = True
    ui.confirmed = False
    journal._render_entry_form(ui, repository, "paper")
    assert not path.exists()
    ui.confirmed = True
    journal._render_entry_form(ui, repository, "paper")
    journal._render_entry_form(ui, repository, "paper")
    assert repository.count_entries(record_type="paper") == 1
    assert repository.list_entries(record_type="paper")[0].entry.net_pnl == Decimal("10.00")
    ui.submitted = False
    journal._render_entry_form(ui, repository, "paper")
    assert repository.count_entries(record_type="paper") == 1


def test_streamlit_journal_initial_load_does_not_write(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("streamlit.testing.v1")
    from streamlit.testing.v1 import AppTest

    path = tmp_path / "ui.db"
    monkeypatch.setattr(journal, "JOURNAL_DB", path)

    def render():
        import streamlit as st
        from qx.ui.pages.journal import render_journal_page
        render_journal_page(st)

    app = AppTest.from_function(render)
    app.query_params.update({"symbol": "TEST", "snapshot": "7", "as_of": "2020-01-01"})
    app.run()
    assert not app.exception
    assert not path.exists()
    initial_inputs = {widget.label: widget.value for widget in app.text_input}
    assert initial_inputs["Symbol"] == "TEST"
    assert initial_inputs["Evidence snapshot reference"] == "snapshot:7"
    assert app.date_input[0].value == date.today()
    app.selectbox(key="outcome_journal_type").set_value("paper").run()
    assert not app.exception
    assert not path.exists()
    inputs = {
        "Symbol": "TEST", "Evidence snapshot reference": "scan:123",
        "Entry price (USD / share)": "100.10", "Exit price (USD / share)": "105.20",
        "Quantity (shares)": "3", "Total round-trip fees and costs (USD)": "1.01",
    }
    for widget in app.text_input:
        widget.set_value(inputs[widget.label])
    for widget in app.text_area:
        widget.set_value("User-entered test note")
    for widget in app.date_input:
        widget.set_value(date(2026, 1, 1))
    app.checkbox[0].set_value(True)
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert len(app.success) == 1
    repository = SQLiteJournalRepository(path)
    assert repository.list_entries(record_type="paper")[0].entry.net_pnl == Decimal("14.29")
    app.run()
    assert not app.exception
    assert repository.count_entries(record_type="paper") == 1
