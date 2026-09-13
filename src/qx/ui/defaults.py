from qx.config.settings import get_settings


MARKET_DATA_PROVIDER_OPTIONS = ["schwab", "yfinance"]
OPTION_CHAIN_PROVIDER_OPTIONS = ["schwab", "yfinance", "none"]


def default_market_data_provider() -> str:
    """Return the preferred market-data provider for UI controls.

    The app should open on Schwab by default because it is the higher-quality
    realtime-capable source. The configured provider remains useful for CLI and
    automation jobs, but UI controls should not silently downgrade to yfinance.
    """
    provider = get_settings().data_provider.strip().lower()
    if provider == "schwab":
        return "schwab"
    return "schwab" if "schwab" in MARKET_DATA_PROVIDER_OPTIONS else provider


def provider_index(options: list[str], preferred: str | None = None) -> int:
    """Return a safe selectbox index for a provider option list."""
    provider = (preferred or default_market_data_provider()).strip().lower()
    return options.index(provider) if provider in options else 0
