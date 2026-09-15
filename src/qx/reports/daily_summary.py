"""Daily System Summary Report Generator for QX Platform."""

from datetime import datetime, timezone
from typing import Any
import math


def generate_daily_system_summary(
    etf_rows: list[dict[str, Any]] | None = None,
    options_ideas: list[dict[str, Any]] | None = None,
    spx_data: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile an executive daily summary report across QX Platform modules."""
    now = datetime.now(timezone.utc)
    
    # 1. Sector Relative Strength Summary
    leading_sectors: list[str] = []
    lagging_sectors: list[str] = []
    if etf_rows:
        for row in etf_rows:
            quadrant = row.get("rs_quadrant")
            sector = row.get("sector", row.get("etf", ""))
            if quadrant == "LEADING" and sector:
                leading_sectors.append(sector)
            elif quadrant == "LAGGING" and sector:
                lagging_sectors.append(sector)

    # 2. Options Ideas Summary
    ideas_count = len(options_ideas) if options_ideas else 0
    top_tickers = [idea.get("symbol") for idea in (options_ideas or [])[:5] if isinstance(idea, dict) and "symbol" in idea]

    # 3. SPX GEX Summary
    spx_close = spx_data.get("spx_close") if spx_data else None
    gamma_flip = spx_data.get("gamma_flip") if spx_data else None

    # 4. Portfolio Health
    portfolio_equity = portfolio.get("total_equity", 0.0) if portfolio else 0.0
    publication_state = portfolio.get("publication_state", "VERIFIED") if portfolio else "VERIFIED"

    return {
        "timestamp": now.isoformat(),
        "summary": {
            "leading_sectors": leading_sectors,
            "lagging_sectors": lagging_sectors,
            "options_ideas_count": ideas_count,
            "top_option_tickers": top_tickers,
            "spx_close": spx_close,
            "spx_gamma_flip": gamma_flip,
            "portfolio_equity": portfolio_equity,
            "publication_state": publication_state,
        },
        "system_status": "OPERATIONAL",
    }
