"""Scratch: can this system actually place a live order? Evidence only."""
import os
import re

ROOT = r"C:\Project\2026\src\qx"

PATTERNS = {
    "client.post(...)": r"\.post\(",
    "accounts/*/orders path": r"accounts/[^\"']{0,40}/orders",
    "place/submit/send order def": r"def\s+(place_order|submit_order|send_order|create_order)",
    "OrderRouter class": r"class OrderRouter",
    "submit_simulated": r"def submit_simulated",
}

print("=== order-submission surfaces across the whole repo ===")
for label, pattern in PATTERNS.items():
    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for match in re.finditer(pattern, text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{os.path.relpath(path, ROOT)}:{line_no}")
    print(f"  {label:<30} {len(hits):>3} hit(s)  {hits[:6]}")

print()
print("=== what does OrderRouter actually do? ===")
router = open(os.path.join(ROOT, "execution", "order_router.py"), encoding="utf-8").read()
for match in re.finditer(r"^(class |    def |def )(.{0,70})", router, re.M):
    print("   ", (match.group(1) + match.group(2)).strip()[:96])
