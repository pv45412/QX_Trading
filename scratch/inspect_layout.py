"""Scratch: measure information density of the Discover page sections."""
import os
import re
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")
from qx.app import ui  # noqa: E402

body = ui.SCANNER_BODY

print("=== SECTOR RANKINGS: columns rendered ===")
idx = body.find("Sector rankings")
seg = body[idx:idx + 3000]
for col in re.findall(r"\{h:'([^']+)'", seg):
    print("   col:", col)

print("\n=== how each sector row is built ===")
m = re.search(r"secRows|SECTORS|sectors\s*\.\s*map|sectorRows", body)
if m:
    print(body[max(0, m.start() - 200):m.start() + 900])

print("\n=== RESULTS: columns rendered ===")
ridx = body.find("Results")
rseg = body[ridx:ridx + 3000]
for col in re.findall(r"\{h:'([^']+)'", rseg):
    print("   col:", col)

print("\n=== KPI / context cards ===")
for m in re.finditer(r"kpi\('([^']+)'", body):
    print("   kpi:", m.group(1))
