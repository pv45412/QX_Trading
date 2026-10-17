"""Broker spellings for known equity share classes; cache identities stay unchanged."""


def schwab_equity_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return {
        "BRK-A": "BRK/A", "BRK.A": "BRK/A",
        "BRK-B": "BRK/B", "BRK.B": "BRK/B",
        "BF-A": "BF/A", "BF.A": "BF/A",
        "BF-B": "BF/B", "BF.B": "BF/B",
    }.get(normalized, normalized)


def schwab_option_chain_symbol(symbol: str) -> str:
    """Return Schwab's option-chain request spelling without changing local identity."""
    normalized = symbol.strip().upper()
    return {
        "SPX": "$SPX",
        "NDX": "$NDX",
        "RUT": "$RUT",
        "VIX": "$VIX",
    }.get(normalized, schwab_equity_symbol(normalized))


def schwab_market_data_symbol(symbol: str) -> str:
    """Return Schwab's root symbol for a supported continuous-futures alias.

    Local callers retain their canonical ``*=F`` identity.  Schwab resolves the
    root to a currently tradable contract, which must still be recorded and
    validated before that quote or history is used as contract evidence.
    """
    normalized = symbol.strip().upper()
    return {
        "SPX": "$SPX",
        "ES=F": "/ES",
        "NQ=F": "/NQ",
        "RTY=F": "/RTY",
        "YM=F": "/YM",
        "CL=F": "/CL",
        "GC=F": "/GC",
    }.get(normalized, schwab_equity_symbol(normalized))
