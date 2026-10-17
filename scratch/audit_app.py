"""Scratch: import-check the app modules."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import trade, ui  # noqa: E402
from qx.app.server import Handler  # noqa: E402

print("IMPORTS OK")
print("scanner body:", len(ui.SCANNER_BODY))
print("trade body  :", len(ui.TRADE_BODY))
reports = ui.reports_page()
print("reports page:", len(reports))
print("has nav link:", "/scanner" in reports and "/reports" in reports)
print("handler     :", Handler.__name__)
