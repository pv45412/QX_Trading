"""Read the token expiry fields and decode Schwab's 400 body (it is gzip)."""
import gzip
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")
from qx.config.settings import get_settings  # noqa: E402

s = get_settings()
tp = Path(r"C:\Project\2026") / s.schwab_token_path
blob = json.loads(tp.read_text(encoding="utf-8"))
for key in ("refresh_token_expires_at", "access_token_expires_at"):
    print(f"{key:26}: {blob.get(key)}")
print("scope                     :", blob.get("scope"))
print("refresh len               :", len(blob.get("refresh_token") or ""))

body = urllib.parse.urlencode({
    "grant_type": "refresh_token",
    "refresh_token": blob["refresh_token"],
    "client_id": s.schwab_client_id,
    "client_secret": s.schwab_client_secret,
}).encode()
req = urllib.request.Request(
    s.schwab_auth_base_url.rstrip("/") + "/token", data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded",
             "Accept-Encoding": "gzip"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        print("HTTP", resp.status, "UNEXPECTED SUCCESS")
except urllib.error.HTTPError as exc:
    raw = exc.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    print("\nHTTP", exc.code)
    print("DECODED BODY:", raw.decode("utf-8", "replace")[:800])
