"""Probe the Schwab refresh token directly against Schwab, bypassing our code.

Establishes whether "refresh token was rejected" is a real broker condition or
an artefact of our auth layer.
"""
import datetime as dt
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
tp = Path(s.schwab_token_path)
if not tp.is_absolute():
    tp = Path(r"C:\Project\2026") / tp

print("token path      :", tp)
print("token exists    :", tp.exists())
if not tp.exists():
    sys.exit("no token file")

blob = json.loads(tp.read_text(encoding="utf-8"))
print("token keys      :", sorted(blob.keys()))
for k in ("creation_timestamp", "expires_in", "token_type", "scope"):
    if k in blob:
        v = blob[k]
        if k == "creation_timestamp" and isinstance(v, (int, float)):
            created = dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc)
            age = dt.datetime.now(dt.timezone.utc) - created
            print(f"{k:16}: {v}  ({created.isoformat()}, age {age})")
        else:
            print(f"{k:16}: {v}")

refresh = blob.get("refresh_token") or ""
print("refresh present :", bool(refresh), "len", len(refresh))
print("access present  :", bool(blob.get("access_token")))

body = urllib.parse.urlencode({
    "grant_type": "refresh_token",
    "refresh_token": refresh,
    "client_id": s.schwab_client_id,
    "client_secret": s.schwab_client_secret,
}).encode()
url = s.schwab_auth_base_url.rstrip("/") + "/token"
req = urllib.request.Request(
    url, data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST",
)
print("\nPOST", url)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))
        payload.pop("access_token", None)
        payload.pop("refresh_token", None)
        print("HTTP", resp.status)
        print("REFRESH SUCCEEDED:", json.dumps(payload, indent=2)[:600])
except urllib.error.HTTPError as exc:
    raw = exc.read().decode("utf-8", "replace")
    print("HTTP", exc.code)
    print("BODY:", raw[:600])
    if exc.code in (400, 401):
        print("\nVERDICT: refresh token is genuinely rejected by Schwab")
except Exception as exc:  # noqa: BLE001
    print("transport error:", type(exc).__name__, exc)
