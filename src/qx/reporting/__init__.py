"""QX read-only account reporting: history, transactions, cost and P&L.

Nothing in this package writes to the broker. It only reads accounts,
transactions and orders from Schwab and computes deterministic reports.
"""
from qx.reporting.pnl_engine import build_report
from qx.reporting.schwab_activity import SchwabActivityReader

__all__ = ["SchwabActivityReader", "build_report"]
