"""Settings service: Schwab credential/connection state (read-only, masked).

Secrets discipline:
  * The client SECRET is never returned, logged or sent to the browser — only
    presence and a masked tail of the client ID.
  * The OAuth access/refresh tokens are never returned either; only their
    lifecycle state.
  * Writing credentials is a separate, explicit action that rewrites the local
    .env file; it is never implied by reading this page.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any

WORKSPACE_ROOT = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"
ENV_PATH = os.path.join(WORKSPACE_ROOT, ".env")


def _settings():
    from qx.config.settings import get_settings

    return get_settings()


def _mask(value: str, keep: int = 4) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return ("*" * max(0, len(text) - keep)) + text[-keep:] if len(text) > keep else "*" * len(text)


def status() -> dict[str, Any]:
    """Credential presence, token lifecycle and provider health. No secrets."""
    out: dict[str, Any] = {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "env_path": ENV_PATH,
        "env_exists": os.path.exists(ENV_PATH),
    }
    try:
        settings = _settings()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"settings unavailable: {type(exc).__name__}: {exc}"[:200]
        return out

    out["client"] = {
        "client_id_present": bool(settings.schwab_client_id),
        "client_id_masked": _mask(settings.schwab_client_id),
        "client_secret_present": bool(settings.schwab_client_secret),
        "redirect_uri": settings.schwab_redirect_uri,
        "auth_base_url": settings.schwab_auth_base_url,
        "api_base_url": settings.schwab_api_base_url,
        "token_path": str(settings.schwab_token_path),
    }

    try:
        from qx.brokers.schwab.auth import SchwabTokenManager

        manager = SchwabTokenManager(settings)
        auth = manager.status()
        out["token"] = {
            "configured": bool(auth.configured),
            "has_token": bool(auth.has_token),
            "access_token_valid": bool(auth.access_token_valid),
            "refresh_token_valid": bool(auth.refresh_token_valid),
            "restart_required": bool(auth.restart_required),
            "message": auth.message,
            # Tri-state refresh lifecycle. `refresh_token_valid` alone cannot
            # distinguish "expired" from "the provider rejected it", which is
            # what the settings page was mis-reporting as healthy.
            "refresh_token_state": auth.refresh_token_state,
            "refresh_expiry_known": bool(auth.refresh_expiry_known),
            "provider_verified": bool(auth.provider_verified),
            "provider_error": auth.provider_error,
        }
        token_file = settings.schwab_token_path
        if not token_file.is_absolute():
            token_file = token_file if token_file.exists() else (settings.schwab_token_path)
        out["token_file_exists"] = bool(getattr(token_file, "exists", lambda: False)())
        out["authorization_url"] = manager.authorization_url() if auth.configured else None
    except Exception as exc:  # noqa: BLE001
        out["token"] = {"message": f"token state unavailable: {type(exc).__name__}: {exc}"[:200]}

    # Provider health is best-effort: a failure is reported, never raised.
    try:
        from qx.brokers.schwab.auth import SchwabTokenManager
        from qx.brokers.schwab.client import SchwabApiClient
        from qx.brokers.schwab.quotes import SchwabQuoteProvider

        client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
        quote = SchwabQuoteProvider(client).get_quote("SPY")
        out["health"] = {
            "ok": True,
            "probe": "GET /marketdata/v1/quotes?symbols=SPY",
            "last": quote.last,
            "realtime": bool(quote.realtime),
            "resolved_symbol": quote.resolved_symbol,
        }
    except Exception as exc:  # noqa: BLE001
        out["health"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200],
                         "probe": "GET /marketdata/v1/quotes?symbols=SPY"}

    out["notes"] = [
        "The client secret is never exposed to the browser, prompts or logs.",
        "Access and refresh tokens stay server-side; only their state is reported.",
        "Writing credentials rewrites the local .env and is a separate explicit action.",
    ]
    return out


def authorize(callback: str) -> dict[str, Any]:
    """Exchange a pasted Schwab callback URL (or bare code) and persist the token.

    WHERE THE CODE GOES: the user pastes the callback URL or `code` value into the
    Settings page. This function hands it to Schwab's token endpoint and writes the
    resulting token SERVER-SIDE to `settings.schwab_token_path`
    (`data/secrets/schwab_token.json`). The browser never receives the token, and the
    user does not have to save it anywhere.

    Schwab authorization codes are single-use and short-lived, so a rejected code
    cannot be retried — the caller must generate a fresh authorization URL.
    """
    text = (callback or "").strip()
    if not text:
        return {"ok": False,
                "error": "Paste the full callback URL (or just the code value) first."}

    try:
        from qx.brokers.schwab.auth import SchwabTokenManager

        settings = _settings()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "error": f"settings unavailable: {type(exc).__name__}: {exc}"[:200]}

    manager = SchwabTokenManager(settings)
    try:
        token = manager.exchange_authorization_code(text)
    except Exception as exc:  # noqa: BLE001
        # Surface Schwab's own reason; the code is single-use so a retry needs a
        # brand-new authorization URL.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}

    return {
        "ok": True,
        "message": "Authorization complete — the token is saved server-side.",
        "token_path": str(settings.schwab_token_path),
        "access_token_expires_at": token.access_token_expires_at.isoformat(),
        "refresh_token_expires_at": (
            token.refresh_token_expires_at.isoformat()
            if token.refresh_token_expires_at is not None
            else None
        ),
        "scope": token.scope,
    }


def accounts_health() -> dict[str, Any]:
    """Read-only trader-API probe across every readable account."""
    try:
        from qx.reporting.schwab_activity import SchwabActivityReader
        from qx.brokers.schwab.auth import SchwabTokenManager
        from qx.brokers.schwab.client import SchwabApiClient

        settings = _settings()
        reader = SchwabActivityReader(
            SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
        )
        refs = reader.accounts()
        return {
            "ok": True,
            "probe": "GET /trader/v1/accounts/accountNumbers",
            "accounts": [{"masked": r.masked, "type": r.account_type} for r in refs],
            "count": len(refs),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "probe": "GET /trader/v1/accounts/accountNumbers",
                "error": f"{type(exc).__name__}: {exc}"[:200]}
