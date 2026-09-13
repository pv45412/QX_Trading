from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal, Inexact, Rounded, Subnormal, localcontext
import hashlib
import json
from pathlib import Path
import socket
from typing import Any

import pytest

from qx.storage.journal import JournalEntry, SQLiteJournalRepository, StoredJournalEntry
from qx.storage.reconciliation import (
    IMPORT_SCHEMA, LIVE_BROKER_SYNC_ENABLED, MAX_IMPORT_BYTES, SCHEMA_VERSION,
    preview_reconciliation,
)
from qx.ui.pages import journal


def outcome(record_id: int = 1, /, **updates: Any) -> StoredJournalEntry:
    entry = JournalEntry(
        record_type="live", symbol="TEST", instrument="equity", side="long",
        decision_date=date(2026, 1, 1), entry_date=date(2026, 1, 2), exit_date=date(2026, 1, 3),
        entry_price=Decimal("100"), exit_price=Decimal("105"), quantity=Decimal("3"),
        fees=Decimal("1.01"), thesis="Synthetic regression fixture",
        evidence_ref="fixture:1", planned_invalidation="Fixture rule",
    )
    return StoredJournalEntry(record_id, "2026-01-04T00:00:00+00:00", replace(entry, **updates))


def execution(number: int = 1, *, closing: bool = False, **updates: object) -> dict[str, object]:
    return {
        "execution_key": hashlib.sha256(f"synthetic-fill:{number}".encode()).hexdigest(),
        "journal_entry_id": 1, "symbol": "TEST", "instrument": "equity", "currency": "USD",
        "status": "executed", "side": "SELL" if closing else "BUY",
        "position_effect": "CLOSING" if closing else "OPENING",
        "executed_at": "2026-01-03T15:00:00Z" if closing else "2026-01-02T15:00:00Z",
        "trade_date": "2026-01-03" if closing else "2026-01-02",
        "quantity": "3", "price": "105" if closing else "100",
        "fees": "0.51" if closing else "0.50",
    } | updates


def envelope(executions: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION, "broker": "schwab",
        "source_scope": "11111111-1111-4111-8111-111111111111",
        "executions": executions if executions is not None else [
            execution(), execution(2, closing=True),
        ],
    }


def payload(executions: list[dict[str, object]] | None = None) -> str:
    return json.dumps(envelope(executions))


def test_exact_match_is_only_an_unverified_import_comparison() -> None:
    entry = outcome()
    preview = preview_reconciliation(payload(), [entry])
    match = preview.comparisons[0]
    assert match.state == "matched_import"
    assert match.issues == ()
    assert match.execution_rows == (1, 2)
    assert match.supplied_net_pnl == Decimal("13.99")
    assert not match.broker_verified
    assert not match.broker_evaluation_eligible
    assert not LIVE_BROKER_SYNC_ENABLED
    assert entry.entry.evidence_status == "user_reported"
    assert entry.entry.status == "closed"
    assert preview.unmatched_executions == ()
    assert (preview.execution_count, preview.journal_count) == (2, 1)
    assert preview_reconciliation(payload(), [entry]) == preview


def test_short_side_and_negative_cash_flow() -> None:
    preview = preview_reconciliation(payload([
        execution(side="SELL"), execution(2, closing=True, side="BUY"),
    ]), [outcome(side="short")])
    assert preview.comparisons[0].state == "matched_import"
    assert preview.comparisons[0].supplied_net_pnl == Decimal("-16.01")


@pytest.mark.parametrize(("change", "issue"), [
    ({"symbol": "OTHER"}, "symbol_mismatch"),
    ({"side": "SELL"}, "entry_side_mismatch"),
    ({"quantity": "2.99999999"}, "entry_quantity_mismatch"),
    ({"quantity": "3.00000001"}, "entry_quantity_mismatch"),
    ({"price": "100.00000001"}, "entry_price_mismatch"),
    ({"fees": "0.50000001"}, "total_fees_mismatch"),
    ({"executed_at": "2026-01-01T15:00:00Z", "trade_date": "2026-01-01"},
     "entry_date_mismatch"),
    ({"position_effect": "CLOSING"}, "missing_entry_executions"),
])
def test_exact_checks_do_not_hide_mismatches(change: dict[str, object], issue: str) -> None:
    match = preview_reconciliation(payload([
        execution() | change, execution(2, closing=True),
    ]), [outcome()]).comparisons[0]
    assert match.state == "mismatch"
    assert issue in match.issues
    assert match.supplied_net_pnl is None
    assert not match.broker_verified


@pytest.mark.parametrize(("change", "issue"), [
    ({"side": "BUY"}, "exit_side_mismatch"),
    ({"quantity": "1"}, "exit_quantity_mismatch"),
    ({"price": "104.99"}, "exit_price_mismatch"),
    ({"executed_at": "2026-01-04T15:00:00Z", "trade_date": "2026-01-04"},
     "exit_date_mismatch"),
])
def test_closing_leg_is_checked_independently(change: dict[str, object], issue: str) -> None:
    match = preview_reconciliation(payload([
        execution(), execution(2, closing=True) | change,
    ]), [outcome()]).comparisons[0]
    assert match.state == "mismatch"
    assert issue in match.issues


def test_split_fills_use_exact_quantity_weighted_price_and_total_fees() -> None:
    rows = [
        execution(1, quantity="1", price="99", fees="0.20"),
        execution(2, quantity="2", price="100.5", fees="0.30"),
        execution(3, closing=True, quantity="1", price="104", fees="0.21"),
        execution(4, closing=True, quantity="2", price="105.5", fees="0.30"),
    ]
    with localcontext() as context:
        context.prec = 6
        match = preview_reconciliation(payload(rows), [outcome()]).comparisons[0]
    assert match.state == "matched_import"
    assert match.supplied_net_pnl == Decimal("13.99")
    rows[1]["price"] = "100.50000001"
    assert "entry_price_mismatch" in preview_reconciliation(
        payload(rows), [outcome()],
    ).comparisons[0].issues


def test_low_decimal_context_does_not_change_large_notional_comparisons() -> None:
    item = outcome(quantity=Decimal("999999999999"), entry_price=Decimal("999999999998"),
                   exit_price=Decimal("999999999999"))
    rows = [execution(price="999999999998", quantity="999999999999"),
            execution(2, closing=True, price="999999999999", quantity="999999999999")]
    with localcontext() as context:
        context.prec = 6
        result = preview_reconciliation(payload(rows), [item]).comparisons[0]
    assert result.state == "matched_import"
    assert result.supplied_net_pnl == Decimal("999999999997.99")


@pytest.mark.parametrize("signal", [Inexact, Rounded])
@pytest.mark.parametrize(("side", "expected"), [("long", "0.01"), ("short", "-0.01")])
def test_caller_rounding_traps_do_not_reject_valid_fractional_share_outcomes(
    signal: type[Inexact] | type[Rounded], side: str, expected: str,
) -> None:
    item = outcome(side=side, entry_price=Decimal("1"), exit_price=Decimal("1.01"),
                   quantity=Decimal("0.5"), fees=Decimal("0"))
    text = payload([
        execution(price="1", quantity="0.5", fees="0", side="BUY" if side == "long" else "SELL"),
        execution(2, closing=True, price="1.01", quantity="0.5", fees="0",
                  side="SELL" if side == "long" else "BUY"),
    ])
    with localcontext() as context:
        context.traps[signal] = True
        context.clear_flags()
        result = preview_reconciliation(text, [item]).comparisons[0]
        assert context.traps[signal]
        assert not any(context.flags.values())
    assert result.state == "matched_import"
    assert result.supplied_net_pnl == Decimal(expected)
    assert not result.broker_verified
    assert not result.broker_evaluation_eligible
    assert item.entry.evidence_status == "user_reported"


def test_caller_exponent_ceiling_does_not_reject_valid_large_notionals() -> None:
    item = outcome(quantity=Decimal("9999"), entry_price=Decimal("9998"),
                   exit_price=Decimal("9999"))
    text = payload([
        execution(price="9998", quantity="9999"),
        execution(2, closing=True, price="9999", quantity="9999"),
    ])
    with localcontext() as context:
        context.Emax = 3
        context.clear_flags()
        result = preview_reconciliation(text, [item]).comparisons[0]
        assert context.Emax == 3
        assert not any(context.flags.values())
    assert result.state == "matched_import"
    assert result.supplied_net_pnl == Decimal("9997.99")


def test_caller_subnormal_trap_does_not_reject_valid_small_fills() -> None:
    item = outcome(quantity=Decimal("0.00000001"), fees=Decimal("0"))
    text = payload([
        execution(quantity="0.00000001", fees="0"),
        execution(2, closing=True, quantity="0.00000001", fees="0"),
    ])
    with localcontext() as context:
        context.Emin = -2
        context.traps[Subnormal] = True
        context.clear_flags()
        result = preview_reconciliation(text, [item]).comparisons[0]
        assert context.Emin == -2
        assert context.traps[Subnormal]
        assert not any(context.flags.values())
    assert result.state == "matched_import"
    assert result.supplied_net_pnl == Decimal("0.00")


@pytest.mark.parametrize(("timestamp", "issue"), [
    ("2026-01-02T15:00:00Z", "ambiguous_execution_order"),
    ("2026-01-02T14:59:59Z", "overlapping_or_reversed_executions"),
])
def test_same_day_order_is_not_guessed(timestamp: str, issue: str) -> None:
    result = preview_reconciliation(payload([
        execution(), execution(2, closing=True, executed_at=timestamp, trade_date="2026-01-02"),
    ]), [outcome(exit_date=date(2026, 1, 2))]).comparisons[0]
    assert result.state == "mismatch"
    assert issue in result.issues


def test_same_day_complete_round_trip_and_timezone_equivalence() -> None:
    result = preview_reconciliation(payload([
        execution(executed_at="2026-01-02T10:00:00-05:00"),
        execution(2, closing=True, executed_at="2026-01-02T15:00:00.000001Z",
                  trade_date="2026-01-02"),
    ]), [outcome(exit_date=date(2026, 1, 2))]).comparisons[0]
    assert result.state == "matched_import"


def test_trade_date_is_eastern_not_utc_or_settlement_date() -> None:
    rows = [execution(executed_at="2026-01-03T00:30:00Z"), execution(2, closing=True)]
    assert preview_reconciliation(payload(rows), [outcome()]).comparisons[0].state == "matched_import"
    rows[0]["trade_date"] = "2026-01-03"
    with pytest.raises(ValueError, match="America/New_York"):
        preview_reconciliation(payload(rows), [outcome()])


def test_missing_close_is_mismatch_not_a_fabricated_outcome() -> None:
    result = preview_reconciliation(payload([execution()]), [outcome()]).comparisons[0]
    assert result.state == "mismatch"
    assert "missing_exit_executions" in result.issues
    assert result.supplied_net_pnl is None


def test_unknown_unassigned_and_missing_links_are_explicit_never_auto_paired() -> None:
    preview = preview_reconciliation(payload([
        execution(journal_entry_id=None), execution(2, closing=True, journal_entry_id=999),
    ]), [outcome()])
    assert preview.comparisons[0].state == "unmatched"
    assert [(item.row, item.reason) for item in preview.unmatched_executions] == [
        (1, "no_journal_link"), (2, "journal_id_outside_preview_scope"),
    ]
    assert preview_reconciliation(payload([]), [outcome()]).comparisons[0].state == "unmatched"
    assert len(preview_reconciliation(payload(), []).unmatched_executions) == 2


def test_review_priority_puts_discrepancies_and_missing_evidence_first() -> None:
    preview = preview_reconciliation(payload([
        execution(), execution(2, closing=True),
        execution(3, journal_entry_id=3, price="101"),
        execution(4, closing=True, journal_entry_id=3),
    ]), [outcome(), outcome(2), outcome(3)])
    assert [(item.journal_entry_id, item.state, item.review_priority) for item in preview.comparisons
            ] == [(3, "mismatch", 1), (2, "unmatched", 2), (1, "matched_import", 3)]
    assert not any(item.broker_evaluation_eligible for item in preview.comparisons)


@pytest.mark.parametrize("record_type", ["paper", "research"])
def test_simulated_and_research_records_cannot_match_live_execution_evidence(record_type: str) -> None:
    updates: dict[str, object] = {"record_type": record_type}
    if record_type == "research":
        updates.update(entry_date=None, exit_date=None, entry_price=None, exit_price=None,
                       quantity=None, fees=Decimal(0))
    result = preview_reconciliation(payload(), [outcome(**updates)]).comparisons[0]
    assert result.state == "unsupported_record"
    assert not result.broker_verified


@pytest.mark.parametrize("change", [{}, {"price": "101"}, {"journal_entry_id": 2}])
def test_duplicate_identity_rejects_repeats_conflicts_and_reallocation(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="Duplicate execution identity"):
        preview_reconciliation(payload([execution(), execution() | change]), [outcome(), outcome(2)])


@pytest.mark.parametrize(("field", "value"), [
    ("quantity", "0"), ("quantity", "-3"), ("quantity", 3), ("quantity", "3e0"),
    ("quantity", "1000000000001"), ("quantity", "0.000000001"),
    ("price", "NaN"), ("price", "Infinity"), ("price", "0"), ("price", True),
    ("fees", None), ("fees", "-0.01"), ("fees", "0.000000001"),
    ("instrument", "option"), ("instrument", "future"), ("currency", "EUR"),
    ("status", "pending"), ("status", "canceled"), ("status", "corrected"),
    ("side", "BUY_TO_CLOSE"), ("side", ""), ("position_effect", "UNKNOWN"),
    ("symbol", "test"), ("symbol", "TEST 100 CALL"),
    ("journal_entry_id", True), ("journal_entry_id", 0), ("journal_entry_id", "1"),
    ("journal_entry_id", 1.0), ("execution_key", "raw-broker-id"),
    ("executed_at", "2026-01-02T15:00:00"), ("executed_at", "2026-01-02T15:00:00+00:99"),
    ("executed_at", "2026-01-02T15:00:00-00:00"),
    ("executed_at", "2026-02-30T15:00:00Z"), ("executed_at", "9999-01-02T15:00:00Z"),
    ("executed_at", "0001-01-01T00:00:00+23:59"),
    ("executed_at", "0001-01-01T00:00:00Z"),
    ("executed_at", "9999-12-31T23:59:59-23:59"),
    ("trade_date", "20260102"), ("trade_date", "2026-01-02T00:00:00Z"),
])
def test_import_rejects_invalid_or_inferred_execution_fields(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        preview_reconciliation(payload([execution() | {field: value}]), [outcome()])


@pytest.mark.parametrize("field", list(execution()))
def test_no_execution_field_is_defaulted(field: str) -> None:
    row = execution()
    del row[field]
    with pytest.raises(ValueError, match="exactly match"):
        preview_reconciliation(payload([row]), [outcome()])


@pytest.mark.parametrize("field", ["accountNumber", "accountHash", "access_token", "netAmount",
                                   "activityId", "transferItems", "orderId"])
def test_unknown_fields_are_rejected_without_echoing_sensitive_input(field: str) -> None:
    secret = "sensitive-fixture-value-never-display"
    for document in [envelope() | {field: secret}, envelope([execution() | {field: secret}])]:
        with pytest.raises(ValueError) as error:
            preview_reconciliation(json.dumps(document), [outcome()])
        assert secret not in str(error.value)
        assert field not in str(error.value)


@pytest.mark.parametrize("change", [
    {"schema_version": "unknown"}, {"broker": "unconfigured"},
    {"source_scope": "not-a-uuid"},
    {"source_scope": "11111111-1111-1111-8111-111111111111"},
    {"executions": {}},
])
def test_import_envelope_contract(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        preview_reconciliation(json.dumps(envelope() | change), [outcome()])


@pytest.mark.parametrize("text", [
    "", "{", "[]", "null", '{"executions": [], "executions": []}',
    "[" * 2000 + "]" * 2000, "\ud800", " " * (MAX_IMPORT_BYTES + 1),
    "\u20ac" * (MAX_IMPORT_BYTES // 3 + 1),
], ids=["empty", "malformed", "array", "null", "duplicate-key", "deep-nesting", "surrogate",
        "oversize-characters", "oversize-bytes"])
def test_invalid_duplicate_recursive_or_oversized_json_is_bounded(text: str) -> None:
    with pytest.raises(ValueError):
        preview_reconciliation(text, [outcome()])


def test_import_and_journal_scope_caps_and_duplicate_scope_ids() -> None:
    rows = [execution(number, journal_entry_id=None) for number in range(500)]
    assert preview_reconciliation(payload(rows), []).execution_count == 500
    with pytest.raises(ValueError, match="500 execution"):
        preview_reconciliation(payload(rows + [execution(501)]), [])
    with pytest.raises(ValueError, match="500 journal"):
        preview_reconciliation(payload([]), [outcome(number) for number in range(1, 502)])
    with pytest.raises(ValueError, match="unique positive"):
        preview_reconciliation(payload(), [outcome(), outcome()])


def test_mutated_invalid_journal_entry_is_revalidated() -> None:
    item = outcome()
    object.__setattr__(item.entry, "quantity", Decimal("NaN"))
    with pytest.raises(ValueError):
        preview_reconciliation(payload(), [item])


def test_preview_never_writes_or_connects_and_preserves_manual_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Reconciliation must not access a network or write a record")

    path = tmp_path / "journal.db"
    repository = SQLiteJournalRepository(path)
    repository.save(outcome().entry, submission_id="synthetic-test-save")
    before = path.read_bytes(), path.stat().st_mtime_ns
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(SQLiteJournalRepository, "save", forbidden)
    entries = repository.list_entries(record_type="live")
    first = preview_reconciliation(payload(), entries)
    assert preview_reconciliation(payload(), entries) == first
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert len(list(tmp_path.iterdir())) == 1
    assert repository.list_entries(record_type="live")[0].entry.evidence_status == "user_reported"
    absent = tmp_path / "absent" / "journal.db"
    preview_reconciliation(payload(), SQLiteJournalRepository(absent).list_entries(record_type="live"))
    assert not absent.parent.exists()


def test_presentation_never_calls_a_manual_or_import_matched_record_reconciled() -> None:
    preview = preview_reconciliation(payload(), [outcome()])
    frame = journal.reconciliation_frame(preview)
    assert frame["Comparison"].tolist() == ["Matches supplied import (unverified)"]
    assert frame["Broker Verified"].tolist() == [False]
    assert frame["Broker Evaluation Eligible"].tolist() == [False]
    assert journal.journal_entries_frame([outcome()])["Evidence Status"].tolist() == ["user_reported"]
    assert "execution_key" not in frame.columns
    assert "source_scope" not in frame.columns
    assert json.loads(json.dumps(IMPORT_SCHEMA))["properties"]["executions"]["maxItems"] == 500


def _render_app() -> None:
    import streamlit as st
    from qx.ui.pages import journal

    journal.render_journal_page(st)


def test_streamlit_preview_is_explicit_read_only_ephemeral_and_privacy_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    path = tmp_path / "journal.db"
    repository = SQLiteJournalRepository(path)
    repository.save(outcome().entry)
    before = path.read_bytes()
    monkeypatch.setattr(journal, "JOURNAL_DB", path)
    app = AppTest.from_function(_render_app).run()
    app.selectbox(key="outcome_journal_type").set_value("live").run()
    assert not app.exception
    assert len(app.dataframe) == 1
    app.text_area(key="outcome_reconciliation_payload").set_value(payload()).run()
    assert len(app.dataframe) == 1
    preview_button = next(item for item in app.button if item.label == "Preview comparison")
    preview_button.click().run()
    assert not app.exception
    assert not app.error
    assert len(app.dataframe) == 2
    assert app.dataframe[1].value["Comparison"].tolist() == ["Matches supplied import (unverified)"]
    assert any("not broker verification" in item.value for item in app.warning)
    assert any("Live broker sync: disabled" in item.value for item in app.caption)
    assert path.read_bytes() == before
    app.run()
    assert len(app.dataframe) == 1  # A rerun does not retain a stale preview.
    app.text_area(key="outcome_reconciliation_payload").set_value(
        json.dumps(envelope() | {"accountNumber": "sensitive-fixture-value"}),
    )
    next(item for item in app.button if item.label == "Preview comparison").click().run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert len(app.error) == 1
    assert "sensitive-fixture-value" not in app.error[0].value
    assert path.read_bytes() == before


def test_streamlit_empty_live_preview_does_not_create_a_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    path = tmp_path / "absent" / "journal.db"
    monkeypatch.setattr(journal, "JOURNAL_DB", path)
    render: Callable[[], None] = _render_app
    app = AppTest.from_function(render).run()
    app.selectbox(key="outcome_journal_type").set_value("live").run()
    app.text_area(key="outcome_reconciliation_payload").set_value(payload())
    next(item for item in app.button if item.label == "Preview comparison").click().run()
    assert not app.exception
    assert app.dataframe[0].value["State"].tolist() == ["Unmatched", "Unmatched"]
    assert not path.parent.exists()
