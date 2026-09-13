from datetime import date
from decimal import InvalidOperation
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

import pandas as pd

from qx.storage.journal import JournalEntry, SQLiteJournalRepository, StoredJournalEntry
from qx.storage.reconciliation import (
    IMPORT_SCHEMA, MAX_IMPORT_BYTES, ReconciliationPreview, preview_reconciliation,
)
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.workspace_context import read_context


JOURNAL_DB = Path("data/scanner_history.db")
RECORD_LABELS = {"research": "Research", "paper": "Paper", "live": "Live (user-reported)"}


def render_journal_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    streamlit.subheader("Outcome Journal")
    streamlit.caption(
        "User-entered records only. Research notes are not trades; paper outcomes are simulated; "
        "live outcomes are self-reported and not broker-verified. No orders are placed."
    )
    streamlit.warning(
        "Closed USD equities only, with quantity in shares and multiplier 1. Options, futures, "
        "open positions, partial exits, and non-USD instruments are unsupported. "
        "No unrealized P&L or automatic signal-to-trade conversion."
    )
    record_type = streamlit.selectbox(
        "Record type", list(RECORD_LABELS), format_func=RECORD_LABELS.get,
        key="outcome_journal_type",
    )
    repository = SQLiteJournalRepository(JOURNAL_DB)
    _render_entry_form(streamlit, repository, record_type)
    _render_saved_entries(streamlit, repository, record_type)


def _render_entry_form(
    streamlit: Any, repository: SQLiteJournalRepository, record_type: str
) -> None:
    context = read_context(getattr(streamlit, "query_params", {}))
    evidence_default = (
        f"snapshot:{context['snapshot']}" if context.get("snapshot") else ""
    )
    with streamlit.form(f"outcome_journal_form_{record_type}"):
        cols = streamlit.columns(2)
        symbol = cols[0].text_input("Symbol", value=context.get("symbol", ""), max_chars=20)
        side = cols[1].selectbox("Long / short", ["long", "short"])
        cols = streamlit.columns(2)
        cols[0].selectbox("Instrument", ["Equity"], disabled=True)
        cols[1].selectbox("Currency", ["USD"], disabled=True)
        decision_date = streamlit.date_input("Decision date", max_value=date.today())
        thesis = streamlit.text_area("Thesis", max_chars=10000)
        evidence_ref = streamlit.text_input(
            "Evidence snapshot reference", value=evidence_default, max_chars=10000,
            help="User-supplied reference, for example scan:137 or snapshot:11. Not verified.",
        )
        invalidation = streamlit.text_area("Planned invalidation", max_chars=10000)
        trade: dict[str, Any] = {}
        if record_type != "research":
            cols = streamlit.columns(2)
            trade["entry_date"] = cols[0].date_input("Entry date", max_value=date.today())
            trade["exit_date"] = cols[1].date_input("Exit date", max_value=date.today())
            cols = streamlit.columns(2)
            trade["entry_price"] = cols[0].text_input("Entry price (USD / share)")
            trade["exit_price"] = cols[1].text_input("Exit price (USD / share)")
            cols = streamlit.columns(2)
            trade["quantity"] = cols[0].text_input("Quantity (shares)")
            trade["fees"] = cols[1].text_input("Total round-trip fees and costs (USD)", value="0")
            streamlit.number_input("Multiplier", value=1, disabled=True)
            streamlit.caption(
                "Net P&L = (exit - entry) x shares x 1 for long; reverse the price difference "
                "for short; subtract entered total fees and costs. Rounded once to USD cents. "
                "No dividends, corporate actions, tax, or unentered costs are included."
            )
        notes = streamlit.text_area("Outcome / review notes", max_chars=10000)
        confirmed = streamlit.checkbox(
            "I confirm these are my research notes."
            if record_type == "research" else
            f"I confirm this is a closed {RECORD_LABELS[record_type].lower()} equity record."
        )
        submitted = streamlit.form_submit_button("Save record", type="primary")
    if not submitted:
        return
    if not confirmed:
        streamlit.error("Confirm the record type before saving.")
        return
    try:
        entry = JournalEntry(
            record_type=record_type, symbol=symbol, instrument="equity", side=side,
            decision_date=decision_date, thesis=thesis, evidence_ref=evidence_ref,
            planned_invalidation=invalidation, outcome_notes=notes, **trade,
        )
        # Keep the same request ID for an unchanged form, including reruns after Save.
        previous = streamlit.session_state.get("outcome_journal_submission")
        if previous is None or previous[0] != entry:
            previous = (entry, str(uuid4()))
            streamlit.session_state["outcome_journal_submission"] = previous
        entry_id = repository.save(entry, submission_id=previous[1])
    except (ValueError, InvalidOperation) as exc:
        streamlit.error(str(exc))
        return
    except (sqlite3.Error, OSError):
        streamlit.error("The journal could not be saved. No success is recorded; retry this form.")
        return
    if entry.net_pnl is None:
        streamlit.success(f"Research record {entry_id} saved. No trade or P&L was recorded.")
    else:
        streamlit.success(
            f"{RECORD_LABELS[record_type]} record {entry_id} saved. "
            f"Net closed P&L: USD {entry.net_pnl:,.2f}."
        )


def _render_saved_entries(
    streamlit: Any, repository: SQLiteJournalRepository, record_type: str
) -> None:
    streamlit.subheader(f"{RECORD_LABELS[record_type]} Records")
    try:
        count = repository.count_entries(record_type=record_type)
        if not count:
            streamlit.info("No saved records in this category.")
            if record_type == "live":
                _render_reconciliation_preview(streamlit, [])
            return
        page_size = 50
        page = int(streamlit.number_input(
            "Records page", min_value=1, max_value=max(1, (count + page_size - 1) // page_size),
            value=1, step=1, key=f"outcome_journal_page_{record_type}",
        ))
        entries = repository.list_entries(
            record_type=record_type, limit=page_size, offset=(page - 1) * page_size,
        )
    except (sqlite3.Error, OSError, ValueError, InvalidOperation):
        streamlit.error("Journal records could not be read or verified. No outcomes are displayed.")
        return
    streamlit.caption(
        f"{count} {RECORD_LABELS[record_type].lower()} records total. "
        "Saved records are append-only; amendments and position reconciliation are not supported. "
        "Execution comparisons do not change record provenance."
    )
    streamlit.dataframe(journal_entries_frame(entries), width="stretch", hide_index=True)
    if entries:
        selected_id = streamlit.selectbox(
            "Record detail", [item.id for item in entries], key=f"outcome_journal_detail_{record_type}",
        )
        item = next(item for item in entries if item.id == selected_id)
        streamlit.caption(f"Recorded at {item.created_at} (UTC). Evidence reference is user-supplied.")
        streamlit.text(f"Evidence: {item.entry.evidence_ref}")
        streamlit.text(f"Thesis: {item.entry.thesis}")
        streamlit.text(f"Planned invalidation: {item.entry.planned_invalidation}")
        streamlit.text(f"Outcome / review: {item.entry.outcome_notes or 'Not entered'}")
    if record_type == "live":
        _render_reconciliation_preview(streamlit, entries)


def _render_reconciliation_preview(streamlit: Any, entries: list[StoredJournalEntry]) -> None:
    streamlit.subheader("Execution Comparison")
    streamlit.caption(
        "Live broker sync: disabled (no configured reconciliation connector). "
        "Read-only import preview; nothing is saved and no accounts or transactions are fetched. "
        "Account IDs, credentials and raw broker payloads are not accepted."
    )
    streamlit.download_button(
        "Download import schema", data=json.dumps(IMPORT_SCHEMA, indent=2),
        file_name="execution_preview_schema.json", mime="application/schema+json",
        key="outcome_reconciliation_schema", icon=":material/download:",
    )
    with streamlit.form("outcome_reconciliation_preview_form"):
        payload = streamlit.text_area(
            "Normalized execution JSON", max_chars=MAX_IMPORT_BYTES,
            key="outcome_reconciliation_payload",
        )
        submitted = streamlit.form_submit_button("Preview comparison")
    if not submitted:
        return
    try:
        preview = preview_reconciliation(payload, entries)
    except (ValueError, InvalidOperation) as exc:
        streamlit.error(str(exc))
        return
    streamlit.warning(
        "Matches mean agreement with user-supplied records, not broker verification. "
        "Manual outcomes remain user-reported and are not broker-reconciled evaluation evidence. "
        "Cross-import reuse, statement completeness and source authenticity are not verified."
    )
    streamlit.caption(
        f"Scope: {preview.journal_count} live records on this page; "
        f"{preview.execution_count} supplied execution rows. "
        "Discrepancies have review priority, followed by missing evidence, then import matches."
    )
    if preview.comparisons:
        streamlit.dataframe(reconciliation_frame(preview), width="stretch", hide_index=True)
    if preview.unmatched_executions:
        streamlit.dataframe(pd.DataFrame([
            {"Import Row": item.row, "State": "Unmatched", "Reason": item.reason}
            for item in preview.unmatched_executions
        ]), width="stretch", hide_index=True)
    if not preview.comparisons and not preview.unmatched_executions:
        streamlit.info("No journal records or executions in this preview.")


def reconciliation_frame(preview: ReconciliationPreview) -> pd.DataFrame:
    labels = {
        "mismatch": "Mismatch", "unmatched": "Unmatched",
        "matched_import": "Matches supplied import (unverified)",
        "unsupported_record": "Unsupported record type",
    }
    return pd.DataFrame([
        {
            "Review Priority": item.review_priority, "Journal Record ID": item.journal_entry_id,
            "Comparison": labels[item.state], "Issues": ", ".join(item.issues) or "None",
            "Import Rows": ", ".join(str(row) for row in item.execution_rows),
            "Supplied Net P&L USD": str(item.supplied_net_pnl)
            if item.supplied_net_pnl is not None else "Not established",
            "Broker Verified": item.broker_verified,
            "Broker Evaluation Eligible": item.broker_evaluation_eligible,
        }
        for item in preview.comparisons
    ])


def journal_entries_frame(entries: list[StoredJournalEntry]) -> pd.DataFrame:
    rows = []
    for item in entries:
        entry = item.entry
        row = {
            "Record ID": item.id, "Record Type": RECORD_LABELS[entry.record_type],
            "Symbol": entry.symbol, "Instrument": "Equity", "Side": entry.side.title(),
            "Status": entry.status.title(), "Decision Date": entry.decision_date.isoformat(),
            "Evidence Reference": entry.evidence_ref,
            "Evidence Status": entry.evidence_status,
        }
        if entry.record_type != "research":
            row.update({
                "Entry Date": str(entry.entry_date), "Exit Date": str(entry.exit_date),
                "Entry USD / Share": f"{entry.entry_price:f}",
                "Exit USD / Share": f"{entry.exit_price:f}",
                "Quantity (Shares)": f"{entry.quantity:f}",
                "Multiplier": f"{entry.multiplier:f}", "Total Fees / Costs USD": f"{entry.fees:f}",
                "Net Closed P&L USD": str(entry.net_pnl),
            })
        rows.append(row)
    return pd.DataFrame(rows)


run_standalone_page("Outcome Journal", "", render_journal_page)
