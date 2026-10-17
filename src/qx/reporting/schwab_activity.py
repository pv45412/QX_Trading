"""Read-only Schwab activity reader: accounts, transactions, orders, positions.

Verified live contract (probed 2026-10):
  * ``GET /trader/v1/accounts/accountNumbers`` -> ``[{accountNumber, hashValue}]``
  * ``GET /trader/v1/accounts?fields=positions`` -> balances + positions
  * ``GET /trader/v1/accounts/{hashValue}/transactions?startDate&endDate``
      - REQUIRES the encrypted ``hashValue``; the plain account number returns
        ``{"message":"Invalid account number"}`` (HTTP 400).
      - usable window is ~1 year; the response is capped (~3000 records), so
        this reader pages in small windows and de-duplicates by ``activityId``.
  * ``GET /trader/v1/accounts/{hashValue}/orders?fromEnteredTime&toEnteredTime``
      - same hash requirement; the window is capped at ~60 days.

This module never sends a write request. Access tokens are used only to build
the Authorization header and are never logged or returned.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from qx.brokers.schwab.client import SchwabApiClient

# Empirical caps; a window returning this many records is treated as truncated.
_TRANSACTION_CAP = 2900
_ORDER_WINDOW_DAYS = 30
_TRANSACTION_WINDOW_DAYS = 30


def _fmt(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@dataclass(frozen=True)
class AccountRef:
    """One account the authenticated token can read."""

    account_number: str
    hash_value: str
    account_type: str | None = None
    label: str = ""

    @property
    def masked(self) -> str:
        num = self.account_number
        return f"••••{num[-4:]}" if len(num) >= 4 else num


@dataclass
class ActivityCollection:
    """Transactions (or orders) with provenance about truncation."""

    transactions: list[dict[str, Any]] = field(default_factory=list)
    windows: int = 0
    truncated_windows: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def truncated(self) -> bool:
        return bool(self.truncated_windows)


class SchwabActivityReader:
    """Thin read-only wrapper over the authenticated Schwab REST client."""

    def __init__(self, client: SchwabApiClient) -> None:
        self.client = client

    # -- discovery ---------------------------------------------------------
    def accounts(self) -> list[AccountRef]:
        """Return every account with its encrypted hash, or an empty list."""
        numbers = self._data(self.client.get("/trader/v1/accounts/accountNumbers"))
        refs: list[AccountRef] = []
        for row in numbers:
            if not isinstance(row, dict):
                continue
            account_number = str(row.get("accountNumber") or "").strip()
            hash_value = str(row.get("hashValue") or "").strip()
            if account_number and hash_value:
                refs.append(AccountRef(account_number=account_number, hash_value=hash_value))
        if not refs:
            return refs
        # Enrich with account type when the positions view is readable.
        try:
            for row in self._data(self.client.get("/trader/v1/accounts", params={"fields": "positions"})):
                securities = row.get("securitiesAccount", row) if isinstance(row, dict) else {}
                number = str(securities.get("accountNumber") or "").strip()
                for index, ref in enumerate(refs):
                    if ref.account_number == number:
                        refs[index] = AccountRef(
                            account_number=ref.account_number,
                            hash_value=ref.hash_value,
                            account_type=str(securities.get("type") or "") or None,
                            label=str(securities.get("type") or ""),
                        )
        except Exception:  # noqa: BLE001 - enrichment is best-effort
            pass
        return refs

    def snapshot(self, account_number: str) -> dict[str, Any]:
        """Balances and positions for one account (read-only)."""
        for row in self._data(self.client.get("/trader/v1/accounts", params={"fields": "positions"})):
            securities = row.get("securitiesAccount", row) if isinstance(row, dict) else {}
            if str(securities.get("accountNumber") or "") != account_number:
                continue
            return {
                "account_number": account_number,
                "type": securities.get("type"),
                "balances": self._dict(securities.get("currentBalances")),
                "initial_balances": self._dict(securities.get("initialBalances")),
                "positions": [
                    p for p in (securities.get("positions") or []) if isinstance(p, dict)
                ],
            }
        return {}

    # -- history -----------------------------------------------------------
    def transactions(self, hash_value: str, days: int = 400) -> ActivityCollection:
        """Page transactions across ``days`` in 30-day windows, de-duplicated."""
        now = dt.datetime.now(dt.timezone.utc)
        oldest = now - dt.timedelta(days=max(1, days))
        seen: dict[Any, dict[str, Any]] = {}
        out = ActivityCollection()
        cursor = oldest
        while cursor < now:
            window_end = min(cursor + dt.timedelta(days=_TRANSACTION_WINDOW_DAYS), now)
            label = cursor.date().isoformat()
            try:
                rows = self._data(
                    self.client.get(
                        f"/trader/v1/accounts/{hash_value}/transactions",
                        params={"startDate": _fmt(cursor), "endDate": _fmt(window_end)},
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one bad window must not kill the report
                out.errors.append(f"{label}: {type(exc).__name__}: {exc}")
                cursor = window_end
                continue
            out.windows += 1
            if len(rows) >= _TRANSACTION_CAP:
                out.truncated_windows.append(label)
            for row in rows:
                if isinstance(row, dict):
                    seen.setdefault(row.get("activityId"), row)
            cursor = window_end
        out.transactions = sorted(
            seen.values(), key=lambda r: str(r.get("time") or ""), reverse=True
        )
        return out

    def orders(self, hash_value: str, days: int = 60) -> ActivityCollection:
        """Read orders; Schwab caps a single request at ~60 days."""
        now = dt.datetime.now(dt.timezone.utc)
        oldest = now - dt.timedelta(days=max(1, min(days, 60)))
        out = ActivityCollection()
        cursor = oldest
        while cursor < now:
            window_end = min(cursor + dt.timedelta(days=_ORDER_WINDOW_DAYS), now)
            label = cursor.date().isoformat()
            try:
                rows = self._data(
                    self.client.get(
                        f"/trader/v1/accounts/{hash_value}/orders",
                        params={
                            "fromEnteredTime": _fmt(cursor),
                            "toEnteredTime": _fmt(window_end),
                            "maxResults": 100,
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001
                out.errors.append(f"{label}: {type(exc).__name__}: {exc}")
                cursor = window_end
                continue
            out.windows += 1
            out.transactions.extend(row for row in rows if isinstance(row, dict))
            cursor = window_end
        return out

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _data(payload: Any) -> list[Any]:
        if isinstance(payload, dict):
            inner = payload.get("data", payload)
            if isinstance(inner, list):
                return inner
            return [inner] if isinstance(inner, dict) else []
        return payload if isinstance(payload, list) else []

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}
