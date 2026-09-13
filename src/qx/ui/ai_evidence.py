"""Read-only bridge to the shared AI service, without a second generation path."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlencode

import requests

from qx.market.dashboard_metrics import DASHBOARD_ETFS
from qx.market.ai_review import validate_rs_evidence
from qx.ui.workspace_context import markets_url, read_context


API_URL = "http://127.0.0.1:8510"
REVIEW_URL = "http://127.0.0.1:5173/"


@dataclass(frozen=True)
class AIReadiness:
    service: str
    evidence_date: str | None = None
    sources: str = ""
    checked_at: str = ""
    issue: str = ""


def review_url(symbol: str, context: Mapping[str, Any] | None = None) -> str:
    if symbol not in DASHBOARD_ETFS.values():
        raise ValueError("Unsupported ETF")
    context = read_context(context or {})
    if context:
        return markets_url(context, etf=symbol, symbol=symbol) + "#ai-review"
    return f"{REVIEW_URL}?{urlencode({'etf': symbol})}#ai-review"


def _get_json(path: str) -> dict[str, Any]:
    response = requests.get(f"{API_URL}{path}", timeout=(1, 4), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError("Local service unavailable")
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Invalid service response")
    return body


def check_ai_readiness(symbol: str) -> AIReadiness:
    review_url(symbol)
    try:
        status = _get_json("/api/ai/status")
        if not all(isinstance(status.get(key), bool) for key in ("enabled", "configured")):
            raise ValueError("Invalid status")
        service = "Disabled" if not status["enabled"] else "Not configured" if not status["configured"] else "Configured; untested"
    except (requests.RequestException, ValueError):
        return AIReadiness("Unavailable", issue="Local AI service is unavailable; readiness is unknown.")

    try:
        evidence = _get_json(f"/api/ai/evidence/{symbol}")
        now = datetime.now(timezone.utc)
        validate_rs_evidence(evidence, now, symbol=symbol, require_live=False)
        checked = datetime.fromisoformat(evidence["checked_at"])
        facts = evidence["facts"]
        sources = []
        for ticker in (symbol, "SPY"):
            source = facts["sources"][ticker]
            fallback = " (fallback)" if source["fallback_used"] else ""
            unverified = " (unverified)" if not source["verified"] else ""
            sources.append(f"{ticker}: {source['actual_source']}{fallback}{unverified}")
        validation = evidence["validation"]
        issue = (f"{validation['status'].capitalize()} local evidence; live generation blocked. "
                 + " ".join(validation["issues"])) if not validation["live_eligible"] else ""
        return AIReadiness(service, facts["bar_date"], " | ".join(sources), checked.strftime("%Y-%m-%d %H:%M UTC"), issue)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return AIReadiness(service, issue="ETF/SPY evidence unavailable or expired. Fresh, aligned price histories with source metadata are required.")


def render_ai_evidence_link(st: Any) -> None:
    context = read_context(getattr(st, "query_params", {}))
    with st.expander("AI evidence review", expanded=False):
        st.caption("Coverage: ETF/SPY daily evidence only. This Command Center snapshot has not been AI-reviewed.")
        names = {symbol: name for name, symbol in DASHBOARD_ETFS.items()}
        symbols = list(names)
        preferred = context.get("etf", "")
        select, check, link = st.columns([2, 1, 1], vertical_alignment="bottom")
        symbol = select.selectbox("ETF", symbols, index=symbols.index(preferred) if preferred in symbols else 0,
                                  format_func=lambda value: f"{value} | {names[value]}",
                                  key="command_ai_etf")
        checked = check.button("Check evidence", key="command_ai_check", icon=":material/fact_check:")
        link.link_button("Open AI review", review_url(symbol, context), icon=":material/open_in_new:")
        if not checked:
            return
        with st.spinner("Checking local evidence..."):
            result = check_ai_readiness(symbol)
        service, evidence = st.columns(2)
        service.metric("Live AI", result.service)
        evidence.metric("ETF/SPY bar date", result.evidence_date or "Unavailable")
        if result.issue:
            st.warning(result.issue)
        requested_date = context.get("as_of")
        if requested_date and result.evidence_date and requested_date != result.evidence_date:
            st.warning(f"Requested date {requested_date} differs from ETF/SPY evidence date {result.evidence_date}. "
                       "This evidence does not validate the requested historical context.")
        if result.sources:
            st.caption(f"{result.sources} | Checked {result.checked_at}")
        st.caption("Readiness check only; no model request was sent.")
