"""Build the focused CODE-REVIEW package.

Two archives are produced:
  * ``QX_code_review.zip``  — source, tests, docs, evidence text. Small, aimed at
    a reviewer who will read the logic. Screenshots and stale run artefacts are
    excluded; the LOGIC_REVIEW document and every test file are included.
  * ``QX_review_package.zip`` — the full working tree (built separately), for
    someone who wants to run it.

Secrets are excluded and the result is verified, exactly as in build_review_zip.py.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_review_zip import EXCLUDE_DIRS, EXCLUDE_EXT, EXCLUDE_FILES, EXCLUDE_PATHS  # noqa: E402

ROOT = r"C:\Project\2026"
OUT = os.path.join(ROOT, "QX_code_review.zip")

# Areas a code reviewer needs.
INCLUDE_TOP = {"src", "web", "tests", "scripts", "tasks", ".agents", "plugin"}
INCLUDE_EXTRA = {
    "QX_LOGIC_REVIEW.md", "QX_Sector_Industry_Explorer_Review.md",
    "QX_Two_Page_Workspace_Plan.md", "README.md", "PROJECT_STATE.md",
    "QX_ROADMAP.md", "QX_BACKLOG.md", "pyproject.toml", ".gitignore",
}
# Evidence worth shipping as TEXT (not the 100 MB of screenshots).
INCLUDE_DATA_EXT = {".md", ".json", ".csv"}

# scratch holds my verification harnesses (worth shipping) plus stale logs/pid
# files and superseded one-off fix scripts (not worth shipping).
SCRATCH_KEEP_PREFIX = ("audit_", "find_", "trace_", "pin_", "probe_", "check_")
SCRATCH_DROP_EXT = {".log", ".pid", ".png"}

# Artefacts that are transient by nature.
DROP_NAME_PATTERNS = (
    re.compile(r"\.pid$"), re.compile(r"-pids\.txt$"), re.compile(r"\.log$"),
    re.compile(r"^nul$"),
)


def looks_like_credential(value: str) -> bool:
    if len(value) < 16 or "/" in value or "\\" in value or " " in value:
        return False
    if value.lower().endswith(".json"):
        return False
    return bool(re.search(r"[A-Za-z]", value)) and bool(re.search(r"[0-9]", value))


def forbidden_values() -> list[str]:
    values: list[str] = []
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if any(t in key.upper() for t in ("SECRET", "CLIENT_ID", "ACCESS_TOKEN",
                                              "REFRESH_TOKEN", "PASSWORD")):
                if looks_like_credential(value):
                    values.append(value)
    token_path = os.path.join(ROOT, "data", "secrets", "schwab_token.json")
    if os.path.exists(token_path):
        import json

        try:
            payload = json.load(open(token_path, encoding="utf-8"))
            for field in ("access_token", "refresh_token"):
                value = str(payload.get(field) or "")
                if looks_like_credential(value):
                    values.append(value)
        except Exception:  # noqa: BLE001
            pass
    return values


def excluded(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in EXCLUDE_DIRS for p in parts[:-1]) or parts[-1] in EXCLUDE_DIRS:
        return True
    for prefix in EXCLUDE_PATHS:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    if parts[-1] in EXCLUDE_FILES:
        return True
    if os.path.splitext(parts[-1])[1].lower() in EXCLUDE_EXT:
        return True
    if any(p.match(parts[-1]) for p in DROP_NAME_PATTERNS):
        return True
    return False


def wanted(rel: str) -> bool:
    parts = rel.split("/")
    top = parts[0]
    ext = os.path.splitext(parts[-1])[1].lower()

    if top in INCLUDE_TOP:
        if top == "web" and ext in {".png", ".jpg", ".jpeg"}:
            return False
        return True
    if top == "scratch":
        return (parts[-1].startswith(SCRATCH_KEEP_PREFIX)
                and ext not in SCRATCH_DROP_EXT)
    if top == "data":
        return ext in INCLUDE_DATA_EXT
    if rel in INCLUDE_EXTRA or "/" not in rel:
        return ext in {".md", ".toml", ".gitignore"} or rel in INCLUDE_EXTRA
    return False


def main() -> int:
    if os.path.exists(OUT):
        os.remove(OUT)
    forbidden = forbidden_values()
    print(f"forbidden secret values loaded: {len(forbidden)}")

    entries: list[str] = []
    raw = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            rel_dir = os.path.relpath(dirpath, ROOT).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirnames[:] = [d for d in dirnames
                           if not excluded((rel_dir + "/" + d).lstrip("/"))]
            for name in filenames:
                rel = (rel_dir + "/" + name).lstrip("/")
                if excluded(rel) or not wanted(rel):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    info = zipfile.ZipInfo.from_file(full, rel)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with open(full, "rb") as handle:
                        archive.writestr(info, handle.read())
                except OSError:
                    continue
                entries.append(rel)
                raw += os.path.getsize(full)

    leaked_names: list[str] = []
    leaked_values: list[str] = []
    names: list[str] = []
    with zipfile.ZipFile(OUT, "r") as archive:
        names = archive.namelist()
        leaked_names = [n for n in names
                        if n.split("/")[-1] in EXCLUDE_FILES
                        or n.startswith("data/secrets/")
                        or (n.startswith(".env") and not n.endswith(".env.example"))]
        for name in names:
            if os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".woff", ".ico"}:
                continue
            try:
                blob = archive.read(name)
            except Exception:  # noqa: BLE001
                continue
            if len(blob) > 8 * 1024 * 1024:
                continue
            text = blob.decode("utf-8", errors="ignore")
            for value in forbidden:
                if value and value in text:
                    leaked_values.append(name)
                    break

    if leaked_names or leaked_values:
        try:
            os.remove(OUT)
            removed = "archive removed"
        except OSError as exc:
            removed = f"could NOT remove ({exc})"
        print("BUILD FAILED:")
        for n in leaked_names[:8]:
            print("    path:", n)
        for n in leaked_values[:8]:
            print("    value in:", n)
        print("   ", removed)
        return 1

    size = os.path.getsize(OUT) / 1024 / 1024
    digest = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    print(f"entries: {len(entries)}   raw: {raw / 1e6:.1f} MB   zip: {size:.1f} MB")
    print("VERIFIED: no secret paths, no secret values")
    print(f"OUTPUT : {OUT}")
    print(f"SHA256 : {digest}")
    import collections

    top = collections.Counter(n.split("/")[0] for n in names)
    print("AREAS  :", dict(top.most_common(10)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
