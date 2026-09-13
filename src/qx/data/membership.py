"""Content-bound membership provenance; retrieval is not an effective date."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
import csv
from io import StringIO
import re

from qx.data.cache import _atomic_write


def membership_symbols(content: bytes) -> list[str]:
    """Reject malformed lists rather than silently dropping suspect records."""
    try:
        rows = list(csv.reader(StringIO(content.decode("utf-8-sig")), strict=True))
    except (csv.Error, UnicodeError) as exc:
        raise ValueError("Membership requires well-formed UTF-8 CSV") from exc
    if (not rows or rows[0].count("symbol") != 1 or any(not name.strip() for name in rows[0])
            or len(set(rows[0])) != len(rows[0])):
        raise ValueError("Membership requires one symbol column and unique nonempty headers")
    header = rows[0]
    index = header.index("symbol")
    symbols = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("Membership row width does not match its header")
        value = row[index]
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", value):
            raise ValueError("Membership contains an invalid symbol")
        symbols.append(value)
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Membership is empty or contains duplicate symbols")
    normalized = [symbol.replace(".", "-") for symbol in symbols]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Membership contains conflicting share-class aliases")
    return symbols


def validate_membership_change(universe: str, symbols: list[str], previous: list[str]) -> None:
    # Operational sanity bounds, not certification of official membership.
    bounds = {"dow_jones": (30, 30), "sp100": (90, 110), "sp500": (490, 520),
              "nasdaq_100": (90, 110), "russell_2000": (1500, 2500)}
    lower, upper = bounds[universe]
    if not lower <= len(symbols) <= upper:
        raise ValueError(f"Unexpected {universe} membership count: {len(symbols)}")
    if previous:
        old, new = set(previous), set(symbols)
        if max(len(old - new), len(new - old)) / len(old) > 0.1:
            raise ValueError("Membership change exceeds 10%; source review required")


def save_membership(path: Path, content: bytes, source: str) -> None:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Membership source must be a nonempty label")
    symbols = membership_symbols(content)
    previous = membership_symbols(path.read_bytes()) if path.exists() else []
    record = {"schema_version": 1, "sha256": sha256(content).hexdigest(),
              "source": source, "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "effective_date": None, "official": False}
    history = {**record, "symbols": symbols, "previous_symbols": previous,
               "added": sorted(set(symbols) - set(previous)),
               "removed": sorted(set(previous) - set(symbols)),
               "baseline": not previous,
               "previous_provenance": membership_provenance(path) if previous else None}
    # Archive the observation before publication. This is not an effective-date history.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    history_dir = path.parent / "membership_history" / path.stem
    history_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(history_dir / f"{stamp}.json",
                  json.dumps(history).encode())
    _atomic_write(path, content)
    _atomic_write(path.with_suffix(".meta.json"), json.dumps(record).encode())


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate membership metadata fields")
        result[key] = value
    return result


def membership_source(content: bytes, metadata: bytes, *, as_of: datetime) -> tuple[str, datetime]:
    """Validate bound retrieval evidence, never official status or effective dates."""
    if as_of.utcoffset() is None:
        raise ValueError("Membership inspection requires an aware clock")
    membership_symbols(content)
    record = json.loads(metadata, object_pairs_hook=_unique_fields)
    if (not isinstance(record, dict) or type(record.get("schema_version")) is not int
            or record["schema_version"] != 1 or record.get("sha256") != sha256(content).hexdigest()):
        raise ValueError("Invalid membership provenance version or digest")
    source, timestamp = record.get("source"), record.get("retrieved_at")
    if not isinstance(source, str) or not source.strip() or not isinstance(timestamp, str):
        raise ValueError("Missing membership source or retrieval time")
    retrieved = datetime.fromisoformat(timestamp)
    if retrieved.utcoffset() is None or retrieved > as_of:
        raise ValueError("Invalid membership retrieval time")
    return source, retrieved


def membership_provenance(path: Path) -> dict[str, Any]:
    unknown = {"status": "Unknown membership provenance", "source": "unknown",
               "retrieved_at": None, "effective_date": None, "official": False}
    try:
        now = datetime.now(timezone.utc)
        source, retrieved = membership_source(path.read_bytes(), path.with_suffix(".meta.json").read_bytes(), as_of=now)
        age = (now - retrieved).total_seconds()
        return {"status": "Stale retrieval; membership unverified" if age >= 86400 else "Recent retrieval; membership unverified",
                "source": source, "retrieved_at": retrieved.isoformat(),
                "effective_date": None, "official": False}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return unknown
