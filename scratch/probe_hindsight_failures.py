"""Scratch: why are the knowledge pages empty when memory clearly works?

Facts so far: 596 nodes, 180 observations, 30 documents, my ingests present.
But the 7 knowledge pages have body "No content yet." and 11 operations FAILED.
Pages carry a mental_model_id, so mental models generate them.
"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8888/v1/default/banks/dsh-memory"


def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return exc.code, raw[:300]
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


print("=== failed operations ===")
status, payload = call("/operations?status=failed&limit=20")
ops = []
if isinstance(payload, dict):
    ops = payload.get("operations") or payload.get("items") or []
elif isinstance(payload, list):
    ops = payload
print(f"  {status}: {len(ops)} returned")
for op in ops[:12]:
    if isinstance(op, dict):
        keys = {k: op.get(k) for k in ("type", "status", "error", "error_message",
                                       "created_at", "kind", "operation_type")}
        print(f"     {json.dumps({k: v for k, v in keys.items() if v is not None})[:230]}")
    else:
        print(f"     {op}")

print("\n=== mental models (these GENERATE the pages) ===")
status, payload = call("/mental-models")
models = []
if isinstance(payload, dict):
    models = payload.get("mental_models") or payload.get("items") or []
elif isinstance(payload, list):
    models = payload
print(f"  {status}: {len(models)} model(s)")
for model in models[:8]:
    if isinstance(model, dict):
        print(f"     id={model.get('id')} name={str(model.get('name'))[:44]} "
              f"status={model.get('status')} last_refresh={str(model.get('last_refreshed_at'))[:19]}")
        if model.get("error"):
            print(f"        ERROR: {str(model.get('error'))[:160]}")

print("\n=== does RECALL work (memory retrieval, not pages)? ===")
status, payload = call("/memories/recall", "POST",
                       {"query": "F23 reference stop study exit rule", "limit": 3})
if isinstance(payload, dict):
    items = payload.get("memories") or payload.get("items") or payload.get("results") or []
    print(f"  {status}: {len(items)} hit(s)")
    for mem in items[:3]:
        text = mem.get("text") if isinstance(mem, dict) else str(mem)
        print(f"     - {str(text)[:130]}")
else:
    print(f"  {status}: {str(payload)[:200]}")

print("\n=== knowledge-base SEARCH (what the tool uses) ===")
status, payload = call("/knowledge-base/search?q=F23+reference+stop")
if isinstance(payload, dict):
    items = payload.get("results") or payload.get("items") or payload.get("pages") or []
    print(f"  {status}: {len(items)} result(s)")
    for item in items[:5]:
        if isinstance(item, dict):
            print(f"     page={item.get('page_id') or item.get('id')} "
                  f"score={item.get('score')} body_len={len(str(item.get('body') or item.get('content') or ''))}")
else:
    print(f"  {status}: {str(payload)[:200]}")
