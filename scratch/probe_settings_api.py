import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8790"


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


for path in ("/api/settings/schwab", "/api/settings/schwab/accounts",
             "/api/schwab/status", "/settings"):
    status, body = get(path)
    print("=" * 78)
    print(f"GET {path}  ->  {status}")
    print("=" * 78)
    if path == "/settings":
        print(f"  [html, {len(body)} bytes]")
        for marker in ("ststamp", "creds", "tok", "hlth", "notes", "loadSettings",
                       "freshChip", "exStamp", "kpi(", "esc(", "j(", "num(", "yn("):
            print(f"    {marker:<14} {'PRESENT' if marker in body else 'MISSING'}")
        continue
    try:
        print(json.dumps(json.loads(body), indent=2)[:2500])
    except Exception:  # noqa: BLE001
        print(body[:1500])
