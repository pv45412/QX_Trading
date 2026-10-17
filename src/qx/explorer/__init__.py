"""QX Sector & Industry Explorer (membership, studies, breadth, entry quality).

IMPORTANT: the submodule ``qx.explorer.ideas`` is deliberately NOT re-exported here
under the name ``ideas``. Python's ``import qx.explorer.ideas as m`` binds the
ATTRIBUTE ``ideas`` of the package, so re-exporting a function with that name
shadows the module and makes it unreachable. Access the engine functions through
:func:`explore` / :func:`catalog`, and the ideas engine through the module
``qx.explorer.ideas``.
"""
from qx.explorer.ideas import build_async, why_ranked
from qx.explorer.membership import (
    UNIVERSE_HOLDINGS,
    UNIVERSE_MEMBERS,
    classified_members,
    fetch_top_holdings,
    parse_holdings_table,
    resolve_universe,
)
from qx.explorer.service import catalog, explore

__all__ = [
    "UNIVERSE_HOLDINGS",
    "UNIVERSE_MEMBERS",
    "build_async",
    "catalog",
    "classified_members",
    "explore",
    "fetch_top_holdings",
    "parse_holdings_table",
    "resolve_universe",
    "why_ranked",
]
