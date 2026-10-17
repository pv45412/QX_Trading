"""Scratch: read the local Hindsight OpenAPI spec to find the real endpoints."""
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8888/openapi.json", timeout=20) as response:
    spec = json.loads(response.read().decode("utf-8"))

info = spec.get("info") or {}
print(f"API: {info.get('title')} v{info.get('version')}")
paths = spec.get("paths") or {}
print(f"endpoints: {len(paths)}\n")

INTERESTING = ("bank", "memor", "page", "observ", "document", "operation", "mental", "retain", "recall")
for path in sorted(paths):
    if any(key in path.lower() for key in INTERESTING):
        methods = ",".join(sorted(m.upper() for m in paths[path] if m in
                                  ("get", "post", "put", "patch", "delete")))
        print(f"  {methods:<20} {path}")

print("\n=== banks that exist ===")
# The spec will show the bank listing route; try the most likely shapes.
for candidate in ("/banks", "/v1/banks", "/api/banks", "/memory-banks"):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8888" + candidate, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
            print(f"  {candidate} -> {json.dumps(payload)[:400]}")
            break
    except Exception:  # noqa: BLE001
        continue
