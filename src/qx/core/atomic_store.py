"""Atomic JSON persistence with explicit corruption reporting (reviewer F19).

Four defects this closes:

1. **Non-atomic writes.** ``open(path, "w")`` truncates the target immediately, so a
   crash, a full disk, or a killed process leaves a half-written file. A reader then
   sees a *valid path* with *invalid content*. Writes here go to a temp file in the
   same directory and are moved into place with ``os.replace``, which is atomic on
   both Windows and POSIX — readers see either the old file or the new one.

2. **Corruption masked as absence.** ``except Exception: return None`` made a corrupt
   file indistinguishable from a missing one, so a damaged order ledger silently
   became "no orders yet" and a damaged snapshot became "no snapshot yet". Reads now
   return a status: ``OK`` / ``MISSING`` / ``CORRUPT``.

3. **Evidence destroyed on recovery.** A corrupt file is quarantined rather than
   overwritten, so the damage can be inspected instead of lost.

4. **Race in job claiming.** ``claim()`` performs the check-and-set under a single
   lock so two callers cannot both believe they own the job.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
from typing import Any, NamedTuple

STATUS_OK = "OK"
STATUS_MISSING = "MISSING"
STATUS_CORRUPT = "CORRUPT"


class ReadResult(NamedTuple):
    payload: Any | None
    status: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    @property
    def corrupt(self) -> bool:
        return self.status == STATUS_CORRUPT


def atomic_write_json(path: str, payload: Any) -> None:
    """Write JSON atomically: temp file in the same directory, then ``os.replace``."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    handle_fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())      # durability before the swap
        os.replace(temp_path, path)        # atomic swap
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def read_json(path: str) -> ReadResult:
    """Read JSON, distinguishing MISSING from CORRUPT rather than conflating them."""
    if not os.path.exists(path):
        return ReadResult(None, STATUS_MISSING, None)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return ReadResult(json.load(handle), STATUS_OK, None)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return ReadResult(None, STATUS_CORRUPT, f"{type(exc).__name__}: {str(exc)[:140]}")
    except OSError as exc:
        return ReadResult(None, STATUS_CORRUPT, f"{type(exc).__name__}: {str(exc)[:140]}")


def quarantine(path: str) -> str | None:
    """Move a corrupt file aside so recovery cannot destroy the evidence."""
    if not os.path.exists(path):
        return None
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = f"{path}.corrupt-{stamp}"
    try:
        os.replace(path, target)
        return target
    except OSError:
        return None


class JobClaim:
    """A single-owner job latch whose check-and-set is atomic.

    ``build_async`` previously tested the running flag OUTSIDE the lock and then
    started a thread, so two callers could both pass the test and both launch.
    ``claim()`` does the test and the set under one lock.
    """

    def __init__(self, fields: tuple[str, ...]) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {name: None for name in fields}
        self._state["running"] = False

    def claim(self, **initial: Any) -> bool:
        """Try to become the owner. False when someone else already is."""
        with self._lock:
            if self._state.get("running"):
                return False
            self._state.update(initial)
            self._state["running"] = True
            return True

    def update(self, **fields: Any) -> None:
        with self._lock:
            self._state.update(fields)

    def increment(self, field: str, amount: int = 1) -> None:
        with self._lock:
            self._state[field] = (self._state.get(field) or 0) + amount

    def release(self, **fields: Any) -> None:
        with self._lock:
            self._state.update(fields)
            self._state["running"] = False
            self._state["current"] = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)
