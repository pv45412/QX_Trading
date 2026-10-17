"""Scratch: which LLM backend is Hindsight using, and is it reachable?"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8888/v1/default/banks/dsh-memory"


def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:300]
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


print("=== bank config (LLM settings live here) ===")
status, payload = call("/config")
if isinstance(payload, dict):
    interesting = {k: v for k, v in payload.items()
                   if any(t in k.lower() for t in ("llm", "model", "provider", "timeout",
                                                   "embed", "reflect", "consolidat"))}
    print(json.dumps(interesting or payload, indent=2)[:1400])
else:
    print(f"  {status}: {str(payload)[:300]}")

print("\n=== LLM health probe (does the backend actually answer?) ===")
status, payload = call("/health/llm", "POST", {})
print(f"  {status}: {json.dumps(payload, indent=2)[:700] if isinstance(payload, dict) else str(payload)[:300]}")

print("\n=== LLM request stats (are calls failing/slow?) ===")
status, payload = call("/llm-requests/stats")
print(f"  {status}: {json.dumps(payload, indent=2)[:800] if isinstance(payload, dict) else str(payload)[:300]}")

print("\n=== recent LLM requests (look for timeouts) ===")
status, payload = call("/llm-requests?limit=6")
items = []
if isinstance(payload, dict):
    items = payload.get("requests") or payload.get("items") or []
elif isinstance(payload, list):
    items = payload
print(f"  {status}: {len(items)} returned")
for item in items[:6]:
    if isinstance(item, dict):
        print(f"     model={item.get('model')} status={item.get('status')} "
              f"ms={item.get('duration_ms')} stage={str(item.get('stage'))[:40]} "
              f"err={str(item.get('error'))[:60]}")
