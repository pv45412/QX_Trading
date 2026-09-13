from qx.ui.defaults import (
    MARKET_DATA_PROVIDER_OPTIONS,
    OPTION_CHAIN_PROVIDER_OPTIONS,
    provider_index,
)


def test_market_data_provider_options_are_schwab_first() -> None:
    assert MARKET_DATA_PROVIDER_OPTIONS[0] == "schwab"
    assert "yfinance" in MARKET_DATA_PROVIDER_OPTIONS


def test_option_chain_provider_options_are_schwab_first() -> None:
    assert OPTION_CHAIN_PROVIDER_OPTIONS[0] == "schwab"
    assert "yfinance" in OPTION_CHAIN_PROVIDER_OPTIONS
    assert "none" in OPTION_CHAIN_PROVIDER_OPTIONS


def test_provider_index_uses_requested_provider_when_available() -> None:
    assert provider_index(MARKET_DATA_PROVIDER_OPTIONS, "schwab") == 0
    assert provider_index(MARKET_DATA_PROVIDER_OPTIONS, "yfinance") == 1


def test_provider_index_falls_back_to_first_option_for_unknown_provider() -> None:
    assert provider_index(MARKET_DATA_PROVIDER_OPTIONS, "bad-provider") == 0
