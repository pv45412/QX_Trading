"""Explicit, user-entered outcomes. No signal ingestion or order execution."""

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from uuid import uuid4

from qx.storage.connection import connect_sqlite


RECORD_TYPES = ("research", "paper", "live")
_DECIMAL_FIELDS = ("entry_price", "exit_price", "quantity", "multiplier", "fees")
_DATE_FIELDS = ("decision_date", "entry_date", "exit_date")


def _amount(value: object, name: str, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be a finite number.") from None
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError(f"{name} must be finite and {'nonnegative' if allow_zero else 'positive'}.")
    exponent = amount.as_tuple().exponent
    assert isinstance(exponent, int)  # Non-finite Decimal exponents were rejected above.
    if amount > Decimal("1000000000000") or exponent < -8:
        raise ValueError(f"{name} must be at most 1 trillion with at most 8 decimal places.")
    with localcontext() as context:
        context.prec = 64
        return amount.normalize()


def _day(value: object, name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{name} must be a date in YYYY-MM-DD format.") from None
        if parsed.isoformat() != value:
            raise ValueError(f"{name} must be a date in YYYY-MM-DD format.")
    else:
        raise ValueError(f"{name} is required and must be a date, not a timestamp.")
    if parsed > date.today():
        raise ValueError(f"{name} cannot be in the future.")
    return parsed


@dataclass(frozen=True)
class JournalEntry:
    record_type: str
    symbol: str
    instrument: str
    side: str
    decision_date: date
    thesis: str
    evidence_ref: str
    planned_invalidation: str
    entry_date: date | None = None
    exit_date: date | None = None
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    quantity: Decimal | None = None
    multiplier: Decimal = Decimal("1")
    fees: Decimal = Decimal("0")
    currency: str = "USD"
    outcome_notes: str = ""

    def __post_init__(self) -> None:
        if self.record_type not in RECORD_TYPES:
            raise ValueError("Record type must be research, paper, or live.")
        if self.instrument != "equity" or self.currency != "USD":
            raise ValueError("Only USD equities are supported; options and futures are disabled.")
        if self.side not in ("long", "short"):
            raise ValueError("Side must be long or short.")
        symbol = self.symbol.strip().upper() if isinstance(self.symbol, str) else ""
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,19}", symbol):
            raise ValueError("Symbol must be an equity ticker (letters, numbers, dots or hyphens).")
        object.__setattr__(self, "symbol", symbol)
        for name in ("thesis", "evidence_ref", "planned_invalidation", "outcome_notes"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value.strip()) > 10000:
                raise ValueError(f"{name} must be text of at most 10,000 characters.")
            if name != "outcome_notes" and not value.strip():
                raise ValueError(f"{name} is required.")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(self, "decision_date", _day(self.decision_date, "Decision date"))
        object.__setattr__(self, "multiplier", _amount(self.multiplier, "Multiplier"))
        object.__setattr__(self, "fees", _amount(self.fees, "Fees", allow_zero=True))
        if self.multiplier != 1:
            raise ValueError("Equity quantity is in shares and multiplier must be 1.")
        if self.record_type == "research":
            if any(getattr(self, key) is not None for key in (
                "entry_date", "exit_date", "entry_price", "exit_price", "quantity",
            )) or self.fees != 0:
                raise ValueError("Research notes cannot contain executions, size, fees, or P&L.")
            return
        for name in ("entry_price", "exit_price", "quantity"):
            object.__setattr__(self, name, _amount(getattr(self, name), name))
        for name in ("entry_date", "exit_date"):
            object.__setattr__(self, name, _day(getattr(self, name), name))
        assert self.entry_date is not None and self.exit_date is not None
        if not self.decision_date <= self.entry_date <= self.exit_date:
            raise ValueError("Dates must be ordered: decision <= entry <= exit.")

    @property
    def net_pnl(self) -> Decimal | None:
        """USD realized price P&L less entered total fees, rounded once to cents."""
        if self.record_type == "research":
            return None
        assert self.entry_price is not None and self.exit_price is not None
        assert self.quantity is not None
        with localcontext() as context:
            context.prec = 64
            direction = Decimal("1") if self.side == "long" else Decimal("-1")
            pnl = ((self.exit_price - self.entry_price) * direction
                   * self.quantity * self.multiplier - self.fees)
            result = pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return abs(result) if result == 0 else result

    @property
    def status(self) -> str:
        return "research" if self.record_type == "research" else "closed"

    @property
    def evidence_status(self) -> str:
        """Provenance is never upgraded by a comparison with user-supplied data."""
        return {"research": "research_note", "paper": "simulated", "live": "user_reported"}[
            self.record_type
        ]


@dataclass(frozen=True)
class StoredJournalEntry:
    id: int
    created_at: str
    entry: JournalEntry


_ENTRY_COLUMNS = tuple(field.name for field in fields(JournalEntry))


class SQLiteJournalRepository:
    """Append-only independent table; opening or reading never creates a database/table."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def save(self, entry: JournalEntry, *, submission_id: str | None = None) -> int:
        # Revalidate before creating a directory, opening SQLite, or writing anything.
        entry = JournalEntry(**{name: getattr(entry, name) for name in _ENTRY_COLUMNS})
        token = submission_id if submission_id is not None else str(uuid4())
        if not isinstance(token, str) or not token.strip() or len(token) > 100:
            raise ValueError("Submission ID must contain 1 to 100 characters.")
        values = tuple(
            str(getattr(entry, name)) if getattr(entry, name) is not None else None
            for name in _ENTRY_COLUMNS
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(connect_sqlite(self.database_path, timeout=10.0)) as connection:
            with connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS journal_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        submission_id TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        record_type TEXT NOT NULL CHECK(record_type IN ('research','paper','live')),
                        symbol TEXT NOT NULL,
                        instrument TEXT NOT NULL CHECK(instrument = 'equity'),
                        side TEXT NOT NULL CHECK(side IN ('long','short')),
                        decision_date TEXT NOT NULL,
                        thesis TEXT NOT NULL,
                        evidence_ref TEXT NOT NULL,
                        planned_invalidation TEXT NOT NULL,
                        entry_date TEXT, exit_date TEXT,
                        entry_price TEXT, exit_price TEXT, quantity TEXT,
                        multiplier TEXT NOT NULL, fees TEXT NOT NULL,
                        currency TEXT NOT NULL CHECK(currency = 'USD'),
                        outcome_notes TEXT NOT NULL,
                        net_pnl TEXT,
                        calculation_version TEXT NOT NULL DEFAULT 'closed_equity_v1'
                    )
                """)
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    f"SELECT id, {', '.join(_ENTRY_COLUMNS)} FROM journal_entries "
                    "WHERE submission_id = ?", (token,),
                ).fetchone()
                if existing is not None:
                    if tuple(existing[1:]) != values:
                        raise ValueError("Submission ID already belongs to a different record.")
                    return int(existing[0])
                columns = ("submission_id", "created_at", *_ENTRY_COLUMNS, "net_pnl")
                cursor = connection.execute(
                    f"INSERT INTO journal_entries ({', '.join(columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)})",
                    (token, datetime.now(UTC).isoformat(), *values,
                     str(entry.net_pnl) if entry.net_pnl is not None else None),
                )
                assert cursor.lastrowid is not None
                return int(cursor.lastrowid)

    def _read(self, query: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        if not self.database_path.is_file():
            return []
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'journal_entries'"
            ).fetchone() is None:
                return []
            return list(connection.execute(query, params).fetchall())

    def list_entries(
        self, *, record_type: str, limit: int = 50, offset: int = 0
    ) -> list[StoredJournalEntry]:
        self._validate_type(record_type)
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("Limit must be 1 to 500 and offset must be nonnegative.")
        rows = self._read(
            "SELECT * FROM journal_entries WHERE record_type = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (record_type, limit, offset),
        )
        entries = []
        for row in rows:
            values = {name: row[name] for name in _ENTRY_COLUMNS}
            for name in _DECIMAL_FIELDS:
                values[name] = Decimal(values[name]) if values[name] is not None else None
            for name in _DATE_FIELDS:
                values[name] = date.fromisoformat(values[name]) if values[name] else None
            entry = JournalEntry(**values)
            expected = str(entry.net_pnl) if entry.net_pnl is not None else None
            if row["net_pnl"] != expected or row["calculation_version"] != "closed_equity_v1":
                raise ValueError("Stored journal calculation failed its integrity check.")
            entries.append(StoredJournalEntry(int(row["id"]), row["created_at"], entry))
        return entries

    def count_entries(self, *, record_type: str) -> int:
        self._validate_type(record_type)
        rows = self._read(
            "SELECT COUNT(*) FROM journal_entries WHERE record_type = ?", (record_type,),
        )
        return int(rows[0][0]) if rows else 0

    @staticmethod
    def _validate_type(record_type: str) -> None:
        if record_type not in RECORD_TYPES:
            raise ValueError("Record type must be research, paper, or live.")
