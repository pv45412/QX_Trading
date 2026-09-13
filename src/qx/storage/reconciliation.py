"""Bounded comparison of user-supplied executions, never a broker connection or write.

Raw broker payloads are deliberately unsupported: activity/transfer items can mix
cash, fees and securities, and order IDs do not identify individual executions.
The caller supplies normalized, complete fills with explicit position effects and
per-fill total costs. No price, side, fee allocation or lot pairing is inferred.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
import json
import re
from typing import Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from qx.storage.journal import JournalEntry, StoredJournalEntry, _amount, _day


MAX_IMPORT_BYTES = 262144
MAX_EXECUTIONS = 500
MAX_JOURNAL_ENTRIES = 500
LIVE_BROKER_SYNC_ENABLED = False
SCHEMA_VERSION = "closed_usd_equity_executions_v1"
_EASTERN = ZoneInfo("America/New_York")
_DECIMAL_PATTERN = r"(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,8})?"
_TIMESTAMP_PATTERN = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)

_EXECUTION_PROPERTIES: dict[str, object] = {
    "execution_key": {
        "type": "string", "pattern": "^[0-9a-f]{64}$",
        "description": "SHA-256 of source_scope + ':' + the stable broker fill ID. "
        "Reuse the same random source_scope for the same broker ledger. "
        "Never supply raw account, order or execution identifiers.",
    },
    "journal_entry_id": {
        "type": ["integer", "null"], "minimum": 1,
        "description": "Explicit local journal record ID, or null when unassigned. No auto-pairing.",
    },
    "symbol": {"type": "string", "pattern": "^[A-Z][A-Z0-9.\\-]{0,19}$"},
    "instrument": {"const": "equity"},
    "currency": {"const": "USD"},
    "status": {"const": "executed"},
    "side": {"enum": ["BUY", "SELL"]},
    "position_effect": {"enum": ["OPENING", "CLOSING"]},
    "executed_at": {"type": "string", "pattern": f"^{_TIMESTAMP_PATTERN}$"},
    "trade_date": {
        "type": "string", "format": "date",
        "description": "Execution date in America/New_York, not settlement or posting date.",
    },
    "quantity": {"type": "string", "pattern": f"^{_DECIMAL_PATTERN}$"},
    "price": {"type": "string", "pattern": f"^{_DECIMAL_PATTERN}$"},
    "fees": {
        "type": "string", "pattern": f"^{_DECIMAL_PATTERN}$",
        "description": "Complete per-execution USD commissions and costs; explicit zero required. "
        "Do not repeat transaction-wide fees across fills or infer fees from net cash.",
    },
}
IMPORT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Read-only, user-supplied closed USD equity execution preview",
    "description": "Maximum 262144 UTF-8 bytes. No account IDs, credentials or raw broker "
    "payloads. Positive quantity/price and nonnegative fees, each at most 1 trillion. "
    "Only complete closed lots, one opening date and one closing date, are supported. "
    "All opening executions must strictly precede all closing executions. "
    "No source authentication, live synchronization, persistence or evaluation certification.",
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "broker", "source_scope", "executions"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "broker": {"enum": ["schwab", "other"]},
        "source_scope": {
            "type": "string", "format": "uuid",
            "description": "Stable random UUID v4 for one broker ledger; never an account ID/hash.",
        },
        "executions": {
            "type": "array", "maxItems": MAX_EXECUTIONS,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": list(_EXECUTION_PROPERTIES), "properties": _EXECUTION_PROPERTIES,
            },
        },
    },
}


@dataclass(frozen=True)
class _Execution:
    row: int
    execution_key: str
    journal_entry_id: int | None
    symbol: str
    side: str
    position_effect: str
    executed_at: datetime
    quantity: Decimal
    price: Decimal
    fees: Decimal


MatchState = Literal["mismatch", "unmatched", "matched_import", "unsupported_record"]


@dataclass(frozen=True)
class JournalComparison:
    journal_entry_id: int
    state: MatchState
    issues: tuple[str, ...]
    execution_rows: tuple[int, ...]
    supplied_net_pnl: Decimal | None = None

    @property
    def review_priority(self) -> int:
        return {"mismatch": 1, "unsupported_record": 1, "unmatched": 2, "matched_import": 3}[
            self.state
        ]

    @property
    def broker_verified(self) -> bool:
        return False

    @property
    def broker_evaluation_eligible(self) -> bool:
        return False


@dataclass(frozen=True)
class UnmatchedExecution:
    row: int
    reason: str


@dataclass(frozen=True)
class ReconciliationPreview:
    comparisons: tuple[JournalComparison, ...]
    unmatched_executions: tuple[UnmatchedExecution, ...]
    execution_count: int
    journal_count: int


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON fields are not permitted.")
        result[key] = value
    return result


def _object(value: object, required: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Import fields must exactly match the normalized schema; "
                         "raw broker payloads and account/credential fields are not accepted.")
    return cast(dict[str, object], value)


def _text(value: object, pattern: str, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise ValueError(f"Invalid {name} format.")
    return value


def _parse_executions(payload: str) -> tuple[_Execution, ...]:
    if not isinstance(payload, str) or len(payload) > MAX_IMPORT_BYTES:
        raise ValueError("Import exceeds the 262144-byte limit or is not JSON text.")
    try:
        if len(payload.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise ValueError("Import exceeds the 262144-byte limit.")
        raw: object = json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Import must be valid bounded UTF-8 JSON.") from None
    root = _object(raw, {"schema_version", "broker", "source_scope", "executions"})
    if root["schema_version"] != SCHEMA_VERSION or root["broker"] not in ("schwab", "other"):
        raise ValueError("Unsupported execution schema version or broker label.")
    scope = _text(root["source_scope"], r"[0-9a-f-]{36}", "anonymous source scope")
    try:
        parsed_scope = UUID(scope)
    except ValueError:
        raise ValueError("Anonymous source scope must be a canonical random UUID v4.") from None
    if str(parsed_scope) != scope or parsed_scope.version != 4:
        raise ValueError("Anonymous source scope must be a canonical random UUID v4.")
    records = root["executions"]
    if not isinstance(records, list) or len(records) > MAX_EXECUTIONS:
        raise ValueError("Import must contain at most 500 execution rows.")
    executions: list[_Execution] = []
    seen: set[str] = set()
    for index, value in enumerate(records, start=1):
        try:
            row = _object(value, set(_EXECUTION_PROPERTIES))
            key = _text(row["execution_key"], r"[0-9a-f]{64}", "execution key")
            if key in seen:
                raise ValueError("Duplicate execution identity; repeated or conflicting fills "
                                 "must be resolved before preview.")
            seen.add(key)
            journal_id = row["journal_entry_id"]
            if journal_id is not None and (type(journal_id) is not int or journal_id < 1):
                raise ValueError("Journal record ID must be a positive integer or null.")
            if (row["instrument"] != "equity" or row["currency"] != "USD"
                    or row["status"] != "executed"):
                raise ValueError("Only executed USD equity fills are supported.")
            symbol = _text(row["symbol"], r"[A-Z][A-Z0-9.\-]{0,19}", "symbol")
            side = _text(row["side"], r"BUY|SELL", "execution side")
            effect = _text(row["position_effect"], r"OPENING|CLOSING", "position effect")
            timestamp = _text(row["executed_at"], _TIMESTAMP_PATTERN, "execution timestamp")
            if timestamp.endswith("-00:00"):
                raise ValueError("Execution timestamp must have a known UTC offset.")
            try:
                executed_at = datetime.fromisoformat(timestamp).astimezone(UTC)
                executed_date = executed_at.astimezone(_EASTERN).date()
            except (ValueError, OverflowError):
                raise ValueError("Invalid execution timestamp.") from None
            if executed_at > datetime.now(UTC):
                raise ValueError("Execution timestamp cannot be in the future.")
            if _day(row["trade_date"], "Trade date") != executed_date:
                raise ValueError("Trade date must equal the execution's America/New_York date.")
            amounts = {
                name: _amount(_text(row[name], _DECIMAL_PATTERN, name), name,
                              allow_zero=name == "fees")
                for name in ("quantity", "price", "fees")
            }
            executions.append(_Execution(
                index, key, journal_id, symbol, side, effect, executed_at,
                amounts["quantity"], amounts["price"], amounts["fees"],
            ))
        except ValueError as exc:
            # Only fixed contract messages are emitted; never echo imported values or keys.
            raise ValueError(f"Execution row {index}: {exc}") from None
    return tuple(executions)


def _compare(item: StoredJournalEntry, executions: Sequence[_Execution]) -> JournalComparison:
    entry = item.entry
    rows = tuple(fill.row for fill in executions)
    if entry.record_type != "live":
        return JournalComparison(item.id, "unsupported_record", ("not_live_user_reported",), rows)
    if not executions:
        return JournalComparison(item.id, "unmatched", ("no_explicitly_linked_executions",), rows)
    issues: list[str] = []
    if any(fill.symbol != entry.symbol for fill in executions):
        issues.append("symbol_mismatch")
    opening = [fill for fill in executions if fill.position_effect == "OPENING"]
    closing = [fill for fill in executions if fill.position_effect == "CLOSING"]
    if opening and closing:
        last_open = max(fill.executed_at for fill in opening)
        first_close = min(fill.executed_at for fill in closing)
        if last_open >= first_close:
            issues.append("ambiguous_execution_order" if last_open == first_close
                          else "overlapping_or_reversed_executions")
    with localcontext() as context:
        context.prec = 80
        for label, fills, expected_date, expected_price, expected_side in (
            ("entry", opening, entry.entry_date, entry.entry_price,
             "BUY" if entry.side == "long" else "SELL"),
            ("exit", closing, entry.exit_date, entry.exit_price,
             "SELL" if entry.side == "long" else "BUY"),
        ):
            if not fills:
                issues.append(f"missing_{label}_executions")
                continue
            if any(fill.executed_at.astimezone(_EASTERN).date() != expected_date for fill in fills):
                issues.append(f"{label}_date_mismatch")
            if any(fill.side != expected_side for fill in fills):
                issues.append(f"{label}_side_mismatch")
            quantity = sum((fill.quantity for fill in fills), Decimal(0))
            if quantity != entry.quantity:
                issues.append(f"{label}_quantity_mismatch")
            # Compare notionals exactly: a rounded average must not certify different fills.
            assert expected_price is not None
            if sum((fill.quantity * fill.price for fill in fills), Decimal(0)) != (
                expected_price * quantity
            ):
                issues.append(f"{label}_price_mismatch")
        fees = sum((fill.fees for fill in executions), Decimal(0))
        if fees != entry.fees:
            issues.append("total_fees_mismatch")
        supplied_pnl = None
        if not issues:
            cash = sum((fill.quantity * fill.price * (1 if fill.side == "SELL" else -1)
                        for fill in executions), Decimal(0))
            supplied_pnl = (cash - fees).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            supplied_pnl = abs(supplied_pnl) if supplied_pnl == 0 else supplied_pnl
            if supplied_pnl != entry.net_pnl:
                issues.append("net_pnl_mismatch")
        return JournalComparison(
            item.id, "mismatch" if issues else "matched_import", tuple(issues), rows, supplied_pnl,
        )


def preview_reconciliation(
    payload: str, entries: Sequence[StoredJournalEntry],
) -> ReconciliationPreview:
    """Compare an explicit bounded journal scope with an untrusted, normalized import.

    Matched means exact agreement with supplied data, not authentic broker evidence.
    No journal record, execution, identity or reconciliation status is persisted.
    Unlinked/out-of-scope rows are reported; a partial import cannot certify a ledger.
    """
    if len(entries) > MAX_JOURNAL_ENTRIES:
        raise ValueError("Preview scope must contain at most 500 journal records.")
    ids: set[int] = set()
    validated: list[StoredJournalEntry] = []
    # Validation and cent rounding must not inherit a caller's decimal traps or exponent limits.
    with localcontext(Context(prec=80)):
        for item in entries:
            if type(item.id) is not int or item.id < 1 or item.id in ids:
                raise ValueError("Preview scope requires unique positive journal record IDs.")
            ids.add(item.id)
            # The public comparison boundary revalidates manual outcomes just like persistence.
            validated.append(StoredJournalEntry(
                item.id, item.created_at, JournalEntry(**vars(item.entry)),
            ))
        executions = _parse_executions(payload)
        grouped: dict[int, list[_Execution]] = {item.id: [] for item in entries}
        unmatched: list[UnmatchedExecution] = []
        for fill in executions:
            if fill.journal_entry_id is None:
                unmatched.append(UnmatchedExecution(fill.row, "no_journal_link"))
            elif fill.journal_entry_id not in ids:
                unmatched.append(UnmatchedExecution(fill.row, "journal_id_outside_preview_scope"))
            else:
                grouped[fill.journal_entry_id].append(fill)
        comparisons = [_compare(item, grouped[item.id]) for item in validated]
    comparisons.sort(key=lambda item: (item.review_priority, item.journal_entry_id))
    return ReconciliationPreview(tuple(comparisons), tuple(unmatched), len(executions), len(entries))
