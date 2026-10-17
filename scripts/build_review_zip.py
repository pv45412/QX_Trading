"""Build a review ZIP of the QX repository.

SECRET DISCIPLINE IS THE POINT OF THIS SCRIPT:
  * .env (live Schwab client id + secret) and data/secrets/* (an OAuth refresh
    token) are EXCLUDED, even though the repo already gitignores them.
  * The archive is scanned after writing; if any excluded name or any known
    secret value appears in the entry list, the build FAILS rather than shipping.

Excluded by design: virtualenvs, node_modules, caches, the .git object store,
byte-code, databases, and the scratch/asar-extract recon dump.
"""
from __future__ import annotations

import hashlib
import os
import zipfile

ROOT = r"C:\Project\2026"
OUT = r"C:\Project\2026\QX_review_package.zip"

# Directory names excluded anywhere in the tree.
EXCLUDE_DIRS = {
    ".venv", "venv", "ENV", "env", "node_modules", ".git", ".pytest_cache",
    "__pycache__", ".mypy_cache", ".ruff_cache", "dist", "build",
    ".phase8-backup", ".vscode",
}
# Directory paths (relative, forward slashes) excluded wholesale.
EXCLUDE_PATHS = {
    "scratch/asar-extract",
    "data/cache",
    "data/processed",
    "data/exports",
    "data/logs",
    "data/secrets",
}
# Exact file names excluded anywhere.
EXCLUDE_FILES = {
    ".env", ".env.local", ".env.production",
    "schwab_token.json", "schwab_tokens.json", "tokens.json",
    ".schwab_tokens.json", "credentials.json",
    "QX_review_package.zip",
}
# Extensions excluded.
EXCLUDE_EXT = {".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3",
               ".db-shm", ".db-wal", ".log", ".token", ".secret", ".pem", ".key",
               ".zip"}

# Values that must never appear in the archive. Read from .env at build time so
# the check is against the REAL secret, not a guess.
def forbidden_values() -> list[str]:
    """Real secret VALUES only.

    A file PATH is not a secret, and `data/secrets/schwab_token.json` legitimately
    appears in .env.example, settings defaults and config tests. So a candidate is
    accepted only if it looks like an opaque credential: no '/' or '\\', no '.json'
    suffix, and a high-entropy mix of letters and digits.
    """
    import re

    def looks_like_credential(value: str) -> bool:
        if len(value) < 16:
            return False
        if "/" in value or "\\" in value or value.lower().endswith(".json"):
            return False
        if " " in value:
            return False
        # An opaque token has both letters and digits, and no obvious prose.
        if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
            return False
        return True

    values: list[str] = []
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                if any(token in key.upper()
                       for token in ("SECRET", "CLIENT_ID", "ACCESS_TOKEN", "REFRESH_TOKEN", "PASSWORD")):
                    if looks_like_credential(value):
                        values.append(value)
    token_path = os.path.join(ROOT, "data", "secrets", "schwab_token.json")
    if os.path.exists(token_path):
        import json

        try:
            with open(token_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for field in ("access_token", "refresh_token"):
                value = str(payload.get(field) or "")
                if looks_like_credential(value):
                    values.append(value)
        except Exception:  # noqa: BLE001
            pass
    return values


def is_excluded(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in EXCLUDE_DIRS for part in parts[:-1]):
        return True
    if parts[-1] in EXCLUDE_DIRS:
        return True
    for prefix in EXCLUDE_PATHS:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    if parts[-1] in EXCLUDE_FILES:
        return True
    if os.path.splitext(parts[-1])[1].lower() in EXCLUDE_EXT:
        return True
    return False


def main() -> int:
    if os.path.exists(OUT):
        os.remove(OUT)

    forbidden = forbidden_values()
    print(f"forbidden secret values loaded: {len(forbidden)}")

    included: list[str] = []
    skipped_secret = 0
    total_bytes = 0

    walker = os.walk(ROOT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for dirpath, dirnames, filenames in walker:
            rel_dir = os.path.relpath(dirpath, ROOT).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirnames[:] = [d for d in dirnames
                           if not is_excluded((rel_dir + "/" + d).lstrip("/"))]
            for name in filenames:
                rel = (rel_dir + "/" + name).lstrip("/")
                if is_excluded(rel):
                    if name in EXCLUDE_FILES or rel.startswith("data/secrets"):
                        skipped_secret += 1
                    continue
                full = os.path.join(dirpath, name)
                try:
                    info = zipfile.ZipInfo.from_file(full, rel)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with open(full, "rb") as handle:
                        archive.writestr(info, handle.read())
                except OSError:
                    continue
                included.append(rel)
                total_bytes += os.path.getsize(full)

    # ---- post-build verification -------------------------------------------
    print(f"entries written: {len(included)}  ({total_bytes / 1024 / 1024:.1f} MB raw)")
    print(f"secret-bearing files skipped: {skipped_secret}")

    leaked_names: list[str] = []
    leaked_values: list[str] = []
    names: list[str] = []
    with zipfile.ZipFile(OUT, "r") as archive:
        names = archive.namelist()
        # `.env.example` is an intentional TEMPLATE (the repo whitelists it in
        # .gitignore). A real `.env*` is never allowed.
        leaked_names = [n for n in names
                        if n.split("/")[-1] in EXCLUDE_FILES
                        or n.startswith("data/secrets/")
                        or (n.startswith(".env") and not n.endswith(".env.example"))]
        # Deep scan: look for any real secret VALUE inside file contents.
        for name in names:
            if os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".gif",
                                                     ".zip", ".woff", ".woff2", ".ico"}:
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
                    leaked_values.append(f"{name} contains a protected value")
                    break

    if leaked_names or leaked_values:
        # The handle is closed by now, so the archive can actually be removed.
        try:
            os.remove(OUT)
            removed = "archive removed"
        except OSError as exc:
            removed = f"archive could NOT be removed ({exc}) — delete it manually"
        print("BUILD FAILED — protected material would have shipped:")
        for item in leaked_names[:10]:
            print("    path:", item)
        for item in leaked_values[:10]:
            print("    value:", item)
        print("   ", removed)
        return 1

    print("VERIFIED: no secret-bearing paths, no secret values in contents")

    digest = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    size_mb = os.path.getsize(OUT) / 1024 / 1024
    print(f"\nOUTPUT : {OUT}")
    print(f"SIZE   : {size_mb:.1f} MB")
    print(f"SHA256 : {digest}")
    top = sorted({n.split('/')[0] for n in names})
    print(f"TOP-LEVEL: {', '.join(top)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
