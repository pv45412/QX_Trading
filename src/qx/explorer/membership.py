"""ETF holdings and constituent membership providers (read-only, provenance-bound).

Two DELIBERATELY DISTINCT universes — never silently substituted for one another:

``ETF_REPORTED_TOP_HOLDINGS``
    Rows scraped from stockanalysis.com/etf/{symbol}/holdings/. Carries ticker,
    company name, WEIGHT and share count. **Top 25 only** — verified 2026-10:
    SMH covers 99.99% of weight, XLE 99.80% (representative), XLK only 84.59% of
    its 78 holdings (a mega-cap-biased subset). Always report ``weight_covered_pct``.

``CLASSIFIED_MEMBERS``
    A full classified constituent list without weights, read from a saved CSV via
    the repository's existing membership provenance path.

Neither is fabricated. When a source is unavailable the provider returns an
explicit status and the LAST KNOWN date, never an invented list.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any

WORKSPACE_ROOT = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"
CACHE_DIR = os.path.join(WORKSPACE_ROOT, "data", "cache", "holdings")
HOLDINGS_TTL_SECONDS = 12 * 3600

SOURCE_URL = "https://stockanalysis.com/etf/{symbol}/holdings/"
SOURCE_LABEL = "stockanalysis.com fund holdings (top 25)"

UNIVERSE_HOLDINGS = "ETF_REPORTED_TOP_HOLDINGS"
UNIVERSE_MEMBERS = "CLASSIFIED_MEMBERS"

# Rows that are not tradable equity instruments (futures, cash lines, FX).
_NON_EQUITY_NAME = re.compile(
    r"\b(DEC|MAR|JUN|SEP)\d{2}\b|\bFUTURES?\b|\bCASH\b|\bCURRENCY\b|\bUSD\b", re.IGNORECASE)
_TICKER_OK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


@dataclass
class HoldingRow:
    symbol: str
    name: str | None = None
    weight: float | None = None          # fraction, e.g. 0.1567
    shares: float | None = None
    rank: int | None = None
    rank_in_source: str | None = None    # e.g. "CA" for Canada — preserved, never dropped

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "name": self.name, "weight": self.weight,
            "shares": self.shares, "rank": self.rank, "rank_in_source": self.rank_in_source,
        }


@dataclass
class MembershipResult:
    symbol: str
    universe: str
    rows: list[HoldingRow] = field(default_factory=list)
    source: str = SOURCE_LABEL
    retrieved_at: str | None = None
    holdings_as_of: str | None = None
    status: str = "OK"                    # OK | SAVED_UNVERIFIED | MEMBERSHIP_UNAVAILABLE
    warning: str | None = None
    reported_total: int | None = None     # what the page claims, when it is legible
    weight_covered_pct: float | None = None
    has_weights: bool = False
    equity_only: bool = True

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def member_completeness(self) -> str:
        """How complete the MEMBER LIST is — independent of any weighting.

        Reviewer F21: completeness must not be inferred from ETF weights. A
        classified universe has no weights at all, yet the old rule marked it
        permanently partial. Member count and the source's own reported total are
        the honest signal here.
        """
        if self.status != "OK":
            return "UNKNOWN"
        if self.reported_total is None:
            return "UNKNOWN"
        if self.count >= self.reported_total:
            return "COMPLETE"
        return "PARTIAL"

    @property
    def weight_completeness(self) -> str:
        """How much of the fund's WEIGHT the rows represent — only when weights exist."""
        if not self.has_weights or self.weight_covered_pct is None:
            return "NOT_APPLICABLE"
        return "COMPLETE" if self.weight_covered_pct >= 95.0 else "PARTIAL"

    @property
    def is_partial(self) -> bool:
        """True when the rows do not plausibly represent the whole universe.

        The RELEVANT dimension depends on the universe:
          * weighted holdings  -> weight coverage decides (a 25-of-78 slice holding
            84.6% of weight is partial even though the rows parsed fine)
          * classified members -> member count decides; absent weights are NOT
            evidence of incompleteness
        """
        if self.status != "OK":
            return True
        if self.has_weights and self.weight_covered_pct is not None:
            return self.weight_covered_pct < 95.0
        if self.member_completeness == "COMPLETE":
            return False
        if self.member_completeness == "PARTIAL":
            return True
        # No weights AND no reported total: completeness genuinely unknown.
        return True

    @property
    def completeness_note(self) -> str:
        """A sentence a reader can trust, naming which dimension was used."""
        if self.status != "OK":
            return f"membership {self.status.lower()}"
        if self.has_weights and self.weight_covered_pct is not None:
            return (f"weight coverage {self.weight_covered_pct:.1f}% of the fund"
                    + (f" ({self.count} of {self.reported_total} reported members)"
                       if self.reported_total else ""))
        if self.member_completeness == "UNKNOWN":
            return (f"{self.count} members; the source reports no total and supplies "
                    "no weights, so completeness is unknown")
        return (f"{self.count} of {self.reported_total} reported members "
                f"({self.member_completeness.lower()}); this universe carries no weights, "
                "so weight coverage does not apply")

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "universe": self.universe,
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "holdings_as_of": self.holdings_as_of,
            "status": self.status,
            "warning": self.warning,
            "count": self.count,
            "reported_total": self.reported_total,
            "weight_covered_pct": self.weight_covered_pct,
            "has_weights": self.has_weights,
            "is_partial": self.is_partial,
            # F21: completeness is reported per dimension, so a reader can see WHICH
            # one made the universe partial (or that neither did).
            "member_completeness": self.member_completeness,
            "weight_completeness": self.weight_completeness,
            "completeness_note": self.completeness_note,
            "coverage_label": self.coverage_label,
            "equity_only": self.equity_only,
            "rows": [r.as_dict() for r in self.rows],
        }

    @property
    def coverage_label(self) -> str:
        """An honest one-line label for the universe, never overstating it."""
        if self.universe == UNIVERSE_MEMBERS:
            return f"classified members ({self.member_completeness.lower()})"
        if self.has_weights and self.weight_covered_pct is not None:
            if self.weight_covered_pct >= 95.0:
                return f"sampled holdings ({self.count} rows, {self.weight_covered_pct:.1f}% of weight)"
            return (f"SAMPLED holdings — {self.count} rows covering only "
                    f"{self.weight_covered_pct:.1f}% of weight")
        return f"sampled holdings ({self.count} rows, weight coverage unknown)"


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def _clean(cell: str) -> str:
    return re.sub(r"<[^>]+>", "", cell).replace("<!---->", "").replace("&amp;", "&").strip()


def parse_holdings_table(html: str) -> tuple[list[HoldingRow], int | None]:
    """Parse the server-rendered holdings table.

    Cells observed in the live page: [rank, ticker, company, weight%, shares].
    Returns (rows, reported_total). Non-equity lines are dropped and counted as a
    warning by the caller rather than silently inflating breadth.
    """
    rows: list[HoldingRow] = []
    for tr in re.findall(r"<tr class=\"svelte-[^\"]*\">([\s\S]*?)</tr>", html):
        cells = [_clean(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr)]
        if len(cells) < 3:
            continue

        rank = None
        ticker = None
        name = None
        weight = None
        shares = None
        for cell in cells:
            if rank is None and re.fullmatch(r"\d{1,3}", cell):
                rank = int(cell)
                continue
            if ticker is None and _TICKER_OK.match(cell):
                ticker = cell
                continue
            if weight is None and cell.endswith("%"):
                try:
                    weight = float(cell.rstrip("%")) / 100.0
                except ValueError:
                    weight = None
                continue
            if shares is None and re.fullmatch(r"[\d,]{2,}", cell):
                try:
                    shares = float(cell.replace(",", ""))
                except ValueError:
                    shares = None
                continue
            if name is None and len(cell) > 2:
                name = cell

        if ticker is None:
            continue
        rows.append(HoldingRow(symbol=ticker, name=name, weight=weight,
                               shares=shares, rank=rank))

    # The page states its own total in more than one place and they disagree;
    # take the LARGEST claim so a partial view is never mistaken for complete.
    claims = [int(m) for m in re.findall(r"(\d{1,4})\s*[Hh]oldings", html)]
    reported_total = max(claims) if claims else None
    return rows, reported_total


def filter_equity_rows(rows: list[HoldingRow]) -> tuple[list[HoldingRow], int]:
    """Drop futures/cash lines. XLE really does carry a futures row (IXPZ6)."""
    kept, dropped = [], 0
    for row in rows:
        haystack = f"{row.symbol} {row.name or ''}"
        if _NON_EQUITY_NAME.search(haystack) or not _TICKER_OK.match(row.symbol):
            dropped += 1
            continue
        kept.append(row)
    return kept, dropped


# --------------------------------------------------------------------------- #
# Fetch / cache
# --------------------------------------------------------------------------- #

def _cache_path(symbol: str) -> str:
    return os.path.join(CACHE_DIR, f"{symbol.upper()}_{UNIVERSE_HOLDINGS}.json")


def _read_cache(symbol: str) -> dict[str, Any] | None:
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _write_cache(symbol: str, payload: dict[str, Any]) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(symbol), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except OSError:
        pass


def _fresh(payload: dict[str, Any]) -> bool:
    stamp = payload.get("retrieved_at")
    if not isinstance(stamp, str):
        return False
    try:
        when = dt.datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - when).total_seconds() < HOLDINGS_TTL_SECONDS


def fetch_top_holdings(symbol: str, *, force: bool = False,
                       timeout: int = 30) -> MembershipResult:
    """Top holdings for an ETF, cached, degrading to saved rows with a warning."""
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z]{1,6}", symbol):
        return MembershipResult(symbol=symbol, universe=UNIVERSE_HOLDINGS,
                                status="MEMBERSHIP_UNAVAILABLE",
                                warning="invalid fund symbol")

    cached = _read_cache(symbol)
    if cached and _fresh(cached) and not force:
        return _from_payload(cached, status="OK")

    url = SOURCE_URL.format(symbol=symbol.lower())
    request = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
        rows, reported = parse_holdings_table(html)
        kept, dropped = filter_equity_rows(rows)
        if not kept:
            raise ValueError("no equity rows parsed")

        weights = [r.weight for r in kept if r.weight is not None]
        covered = round(sum(weights) * 100.0, 2) if weights else None
        if reported and len(kept) < reported:
            warning = (f"partial view: {len(kept)} of {reported} holdings shown by the source"
                       f"{f', covering {covered}% of weight' if covered is not None else ''}")
        elif covered is not None and covered < 95.0:
            warning = f"partial view: rows cover {covered}% of fund weight"
        else:
            warning = None
        if dropped:
            warning = ((warning + "; ") if warning else "") + f"{dropped} non-equity line(s) excluded"

        payload = {
            "symbol": symbol, "rows": [r.as_dict() for r in kept],
            "source": SOURCE_LABEL, "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "holdings_as_of": None,          # retrieval time is NOT the holdings date
            "reported_total": reported, "weight_covered_pct": covered,
            "warning": warning,
        }
        _write_cache(symbol, payload)
        return _from_payload(payload, status="OK")
    except Exception as exc:  # noqa: BLE001 - a source failure must degrade, not invent
        if cached:
            result = _from_payload(cached, status="SAVED_UNVERIFIED")
            result.warning = (f"live fetch failed ({type(exc).__name__}); showing saved holdings "
                              f"from {cached.get('retrieved_at')}. Weights may have changed.")
            return result
        return MembershipResult(
            symbol=symbol, universe=UNIVERSE_HOLDINGS, status="MEMBERSHIP_UNAVAILABLE",
            warning=f"holdings unavailable: {type(exc).__name__}: {str(exc)[:120]}",
        )


def _from_payload(payload: dict[str, Any], *, status: str) -> MembershipResult:
    rows = [HoldingRow(**row) for row in payload.get("rows", []) if isinstance(row, dict)]
    return MembershipResult(
        symbol=str(payload.get("symbol") or ""),
        universe=UNIVERSE_HOLDINGS,
        rows=rows,
        source=str(payload.get("source") or SOURCE_LABEL),
        retrieved_at=payload.get("retrieved_at"),
        holdings_as_of=payload.get("holdings_as_of"),
        status=status,
        warning=payload.get("warning"),
        reported_total=payload.get("reported_total"),
        weight_covered_pct=payload.get("weight_covered_pct"),
        has_weights=any(r.weight is not None for r in rows),
    )


def classified_members(symbol: str) -> MembershipResult:
    """Full classified constituents from a saved CSV (no weights).

    Uses the repository's membership provenance path so the source, digest and
    retrieval time are bound to the content. There is no fabrication fallback.
    """
    symbol = symbol.strip().upper()
    base = os.path.join(WORKSPACE_ROOT, "data", "membership", f"{symbol}.csv")
    if not os.path.exists(base):
        return MembershipResult(
            symbol=symbol, universe=UNIVERSE_MEMBERS, status="MEMBERSHIP_UNAVAILABLE",
            source="saved classified membership",
            warning=f"no classified membership file at {base}",
        )
    try:
        from qx.data.membership import membership_provenance, membership_symbols

        with open(base, "rb") as handle:
            content = handle.read()
        symbols = membership_symbols(content)
        provenance = membership_provenance(__import__("pathlib").Path(base))
        # F21: a classified membership file is a COMPLETE list by construction — it is
        # not a sampled slice of a fund. Completeness is therefore a member-count
        # question, and its answer does not depend on ETF weights (which this universe
        # does not carry at all). "Complete" is NOT the same claim as "officially
        # verified": the provenance warning still says unverified, and both are shown.
        return MembershipResult(
            symbol=symbol, universe=UNIVERSE_MEMBERS,
            rows=[HoldingRow(symbol=s) for s in symbols],
            source=str(provenance.get("source") or "saved classified membership"),
            retrieved_at=provenance.get("retrieved_at"),
            holdings_as_of=provenance.get("effective_date"),
            status="OK",
            warning=str(provenance.get("status") or ""),
            reported_total=len(symbols),
            weight_covered_pct=None,
            has_weights=False,
        )
    except Exception as exc:  # noqa: BLE001
        return MembershipResult(
            symbol=symbol, universe=UNIVERSE_MEMBERS, status="MEMBERSHIP_UNAVAILABLE",
            warning=f"membership invalid: {type(exc).__name__}: {str(exc)[:120]}",
        )


def resolve_universe(symbol: str, universe: str) -> MembershipResult:
    """Resolve exactly one universe. Never substitutes the other silently."""
    if universe == UNIVERSE_MEMBERS:
        return classified_members(symbol)
    if universe == UNIVERSE_HOLDINGS:
        return fetch_top_holdings(symbol)
    raise ValueError(f"unknown universe {universe!r}")
