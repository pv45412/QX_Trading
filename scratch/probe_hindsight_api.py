"""Scratch: query the local Hindsight server to see what is actually stored."""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8888"
BANK = "dsh-memory"

CANDIDATES = [
    "/health",
    "/docs",
    "/openapi.json",
    "/v1/banks",
    "/v1/banks/{bank}",
    "/v1/banks/{bank}/memories",
    "/v1/banks/{bank}/pages",
    "/v1/banks/{bank}/observations",
    "/v1/banks/{bank}/documents",
    "/v1/banks/{bank}/mental-models",
    "/v1/operations",
    "/banks",
    "/banks/{bank}/memories",
]


def get(path):
    url = BASE + path.format(bank=BANK)
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


print(f"probing {BASE} for bank={BANK}\n")
for path in CANDIDATES:
    status, body = get(path)
    if status == 200:
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                keys = sorted(payload.keys())[:8]
                # Try to find a count.
                count = None
                for key in ("total", "count", "items", "data", "results", "memories", "pages"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        count = len(value)
                        break
                    if isinstance(value, int):
                        count = value
                        break
                print(f"  {path:<40} 200  keys={keys} count={count}")
                if count is not None and count == 0:
                    print(f"       -> EMPTY")
                elif count:
                    sample = None
                    for key in ("items", "data", "results", "memories", "pages"):
                        if isinstance(payload.get(key), list) and payload[key]:
                            sample = payload[key][0]
                            break
                    if sample:
                        print(f"       sample: {json.dumps(sample)[:180]}")
            else:
                print(f"  {path:<40} 200  ({type(payload).__name__}, len={len(payload)})")
        except json.JSONDecodeError:
            print(f"  {path:<40} 200  (non-JSON, {len(body)} bytes)")
    elif status is None:
        print(f"  {path:<40} ERR  {body[:60]}")
    else:
        print(f"  {path:<40} {status}")
