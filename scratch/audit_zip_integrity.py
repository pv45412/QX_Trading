"""Scratch: final integrity check of both review archives."""
import ast
import os
import zipfile

ROOT = r"C:\Project\2026"
MUST = [
    "QX_LOGIC_REVIEW.md",
    "src/qx/explorer/momo_trend.py",
    "src/qx/explorer/market_phases.py",
    "src/qx/explorer/master_auto.py",
    "src/qx/explorer/membership.py",
    "src/qx/explorer/service.py",
    "src/qx/explorer/ideas.py",
    "src/qx/app/ui.py",
    "src/qx/app/server.py",
    "web/tests/qx-trade-ideas.cjs",
    "web/tests/qx-explorer.cjs",
]

lines: list[str] = []
for name in ("QX_code_review.zip", "QX_review_package.zip"):
    path = os.path.join(ROOT, name)
    lines.append(f"===== {name} =====")
    if not os.path.exists(path):
        lines.append("  MISSING")
        continue
    archive = zipfile.ZipFile(path)
    lines.append("  integrity : " + ("OK" if archive.testzip() is None else "CORRUPT"))
    names = archive.namelist()
    lines.append(f"  entries   : {len(names)}")
    missing = [m for m in MUST if m not in names]
    lines.append("  key files : " + ("ALL PRESENT" if not missing else f"MISSING {missing}"))
    bad = [n for n in names
           if n.endswith(".env") or "data/secrets/" in n or n.endswith(".pyc")]
    lines.append("  secrets   : " + ("none" if not bad else str(bad[:4])))
    failed = []
    for entry in names:
        if not entry.endswith(".py"):
            continue
        try:
            ast.parse(archive.read(entry).decode("utf-8", "replace"))
        except SyntaxError as exc:
            failed.append(f"{entry}: {exc.msg}")
    lines.append("  python    : " + ("all parse" if not failed else f"{len(failed)} failed"))
    lines.extend("       " + f for f in failed[:5])
    lines.append("  size      : %.1f MB" % (os.path.getsize(path) / 1e6))
    archive.close()

with open(os.path.join(ROOT, "scratch", "zip_report.txt"), "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines))
print("\n".join(lines))
