from typing import Any

from qx.brokers.schwab.auth import SchwabAuthError, SchwabTokenManager
from qx.brokers.schwab.config import save_schwab_env
from qx.brokers.schwab.health import check_schwab_health, schwab_readiness
from qx.config.settings import get_settings
from qx.ui.app_shell import ensure_app_styles, run_standalone_page


def render_schwab_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    streamlit.subheader("Schwab API")
    streamlit.caption("Token health, refresh readiness, and authorization setup.")

    _setup_form(streamlit)
    settings = get_settings()
    manager = SchwabTokenManager(settings)
    status = manager.status()
    readiness = schwab_readiness(status)

    cols = streamlit.columns(5)
    cols[0].metric("Configured", "Yes" if status.configured else "No")
    cols[1].metric("Token File", "Yes" if status.has_token else "No")
    cols[2].metric("Access Token", "Valid" if status.access_token_valid else "Refresh needed")
    cols[3].metric("Refresh Token", "Valid" if status.refresh_token_valid else "Expired/Missing")
    cols[4].metric("Readiness", readiness.label)

    if status.restart_required:
        streamlit.error(status.message)
    elif status.access_token_valid:
        streamlit.success(status.message)
    else:
        streamlit.warning(status.message)
    streamlit.info(f"Next action: {readiness.action}")
    if status.authorization_url:
        streamlit.subheader("Authorization URL")
        streamlit.code(status.authorization_url)
        streamlit.link_button("Open Schwab authorization", status.authorization_url)
        streamlit.caption(
            "Use this only when the refresh token is missing or expired. "
            "Schwab authorization codes are one-time use, so open a fresh URL and save the callback immediately. "
            "Do not paste client secret or tokens into chat."
        )
        _exchange_form(streamlit, manager)

    if streamlit.button("Run Schwab health check"):
        with streamlit.spinner("Checking Schwab auth and SPY market data..."):
            health = check_schwab_health(manager)
        if health.market_data_ok:
            streamlit.success(health.message)
        else:
            streamlit.error(health.message)

    streamlit.subheader("Data Coverage")
    streamlit.caption("What the app can currently source from Schwab versus cached fallback data.")
    streamlit.dataframe(_schwab_capability_rows(), width="stretch", hide_index=True)

    streamlit.subheader("Local .env Template")
    streamlit.code(
        "\n".join(
            [
                "QX_SCHWAB_CLIENT_ID=your_app_key",
                "QX_SCHWAB_CLIENT_SECRET=your_app_secret",
                "QX_SCHWAB_REDIRECT_URI=https://127.0.0.1",
                "QX_SCHWAB_TOKEN_PATH=data/secrets/schwab_token.json",
            ]
        ),
        language="dotenv",
    )

    streamlit.subheader("Configured App Reference")
    streamlit.write("- App: QX-Schwab-Realtime-Bridge")
    streamlit.write("- Environment: Production")
    streamlit.write("- Status: Ready For Use")
    streamlit.write("- Callback URL: https://127.0.0.1")
    streamlit.write("- APIs: Accounts and Trading Production, Market Data Production")
    streamlit.code(
        'powershell -ExecutionPolicy Bypass -File scripts\\configure_schwab.ps1 -ClientId "your_app_key"',
        language="powershell",
    )


def _setup_form(streamlit: Any) -> None:
    with streamlit.expander("Setup Schwab credentials", expanded=False):
        streamlit.caption("Credentials are saved only to local .env, which is ignored by git.")
        client_id = streamlit.text_input("Client ID", value="", type="default")
        client_secret = streamlit.text_input("Client Secret", value="", type="password")
        redirect_uri = streamlit.text_input("Redirect URI", value="https://127.0.0.1")
        if streamlit.button("Save Schwab credentials"):
            try:
                save_schwab_env(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                )
                streamlit.success("Saved Schwab credentials to local .env. Restarted settings will load on refresh.")
            except Exception as exc:
                streamlit.error(f"Could not save Schwab credentials: {exc}")


def _exchange_form(streamlit: Any, manager: SchwabTokenManager) -> None:
    with streamlit.expander("Exchange authorization code", expanded=False):
        streamlit.caption(
            "After login, Schwab redirects to https://127.0.0.1. "
            "Paste the full callback URL or only the code value here. Use a newly generated callback; reused codes fail."
        )
        authorization_code = streamlit.text_input("Authorization code or callback URL", value="", type="password")
        if streamlit.button("Save Schwab token"):
            try:
                if not authorization_code.strip():
                    raise ValueError("Authorization code is required.")
                manager.exchange_authorization_code(authorization_code)
                streamlit.success("Saved Schwab token. Refresh this page to see token status.")
            except SchwabAuthError as exc:
                streamlit.error(str(exc))
            except Exception as exc:
                streamlit.error(f"Could not exchange authorization code: {exc}")


def _schwab_capability_rows() -> list[dict[str, str]]:
    return [
        {
            "Area": "Daily price history",
            "Current Source": "Schwab primary, yfinance fallback",
            "Used By": "Scanner, watchlist, sector rotation, futures dashboard",
        },
        {
            "Area": "Options chains",
            "Current Source": "Schwab primary",
            "Used By": "Options ideas and contract validation",
        },
        {
            "Area": "EMA timing",
            "Current Source": "Schwab primary",
            "Used By": "Options timing and intraday alignment",
        },
        {
            "Area": "Fundamentals",
            "Current Source": "Cached fundamentals fallback",
            "Used By": "Quality engine, income suitability, market movers",
        },
        {
            "Area": "Symbol metadata",
            "Current Source": "Local cache with enrichment fallback",
            "Used By": "Sector, industry, heatmap, reports",
        },
    ]


run_standalone_page(
    "Schwab API",
    "Check Schwab auth configuration and token refresh readiness.",
    render_schwab_page,
)
