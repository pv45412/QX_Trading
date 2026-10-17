"""Scratch: syntax-check every embedded page script (scanner, trade, reports)."""
import os
import re
import subprocess
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import ui  # noqa: E402
from qx.reporting.dashboard import DASHBOARD_HTML  # noqa: E402

node = r"C:\Users\preet\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
pages = {
    "scanner": ui.shell("QX Scanner", ui.SCANNER_BODY),
    "trade": ui.shell("QX Trade Workspace", ui.TRADE_BODY),
    "reports": ui.reports_page(),
}

failures = 0
for name, html in pages.items():
    blocks = re.findall(r"<script>([\s\S]*?)</script>", html)
    print(f"[{name}] script blocks: {len(blocks)}")
    for index, code in enumerate(blocks):
        path = os.path.join(r"C:\Project\2026\scratch", f"page_{name}_{index}.js")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(code)
        result = subprocess.run([node, "--check", path], capture_output=True, text=True)
        status = "OK" if result.returncode == 0 else "SYNTAX ERROR"
        print(f"   block {index}: {len(code)} chars -> {status}")
        if result.returncode != 0:
            failures += 1
            print("      ", (result.stderr or "").strip().splitlines()[0:4])

print("\nALL SCRIPTS VALID" if failures == 0 else f"\n{failures} SCRIPT(S) INVALID")
sys.exit(1 if failures else 0)
