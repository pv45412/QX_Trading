"""Scratch: extract the reports <script> and syntax-check it."""
import os
import re
import subprocess
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.reporting.dashboard import DASHBOARD_HTML

scripts = re.findall(r"<script>([\s\S]*?)</script>", DASHBOARD_HTML)
print("script blocks:", len(scripts))
code = max(scripts, key=len) if scripts else ""
print("largest script chars:", len(code))
out = os.path.join(r"C:\Project\2026\scratch", "reports_script.js")
with open(out, "w", encoding="utf-8") as handle:
    handle.write(code)

node = r"C:\Users\preet\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
res = subprocess.run([node, "--check", out], capture_output=True, text=True)
print("node --check exit:", res.returncode)
if res.stdout.strip():
    print("stdout:", res.stdout[:600])
if res.stderr.strip():
    print("stderr:", res.stderr[:1200])

# Show the offending region if the checker points at a line.
match = re.search(r":(\d+)\n", res.stderr or "")
if match:
    line_no = int(match.group(1))
    lines = code.splitlines()
    print(f"\n--- lines {max(1, line_no - 4)}..{line_no + 2} ---")
    for i in range(max(1, line_no - 4), min(len(lines), line_no + 2) + 1):
        print(f"{i:>5}: {lines[i - 1]}")
