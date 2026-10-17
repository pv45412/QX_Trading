"""Scratch: read the true state of the dsh-memory bank."""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8888/v1/default/banks"
BANK = "dsh-memory"


def get(path):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


print("=== banks ===")
status, payload = get("")
print(f"  {status}: {json.dumps(payload)[:400]}")

print("\n=== stats ===")
status, payload = get(f"/{BANK}/stats")
print(f"  {status}: {json.dumps(payload, indent=2)[:900]}")

print("\n=== documents (my ingested corrections/notes) ===")
status, payload = get(f"/{BANK}/documents")
if isinstance(payload, dict):
    items = payload.get("documents") or payload.get("items") or payload.get("data") or []
    print(f"  {status}: {len(items)} document(s)")
    for doc in items[:8]:
        title = doc.get("title") or doc.get("name") or doc.get("id")
        print(f"     - {str(title)[:90]}")
elif payload:
    print(f"  {status}: {json.dumps(payload)[:300]}")

print("\n=== memories (count + sample) ===")
status, payload = get(f"/{BANK}/memories/list?limit=5")
if isinstance(payload, dict):
    items = payload.get("memories") or payload.get("items") or []
    print(f"  {status}: total={payload.get('total')} returned={len(items)}")
    for mem in items[:3]:
        print(f"     - {json.dumps(mem)[:150]}")
elif payload:
    print(f"  {status}: {json.dumps(payload)[:300]}")

print("\n=== operations (pending work) ===")
status, payload = get(f"/{BANK}/operations")
if isinstance(payload, dict):
    items = payload.get("operations") or payload.get("items") or []
    print(f"  {status}: {len(items)} operation(s)")
    for op in items[:8]:
        print(f"     - type={op.get('type')} status={op.get('status')} "
              f"created={str(op.get('created_at'))[:19]}")
elif payload:
    print(f"  {status}: {json.dumps(payload)[:300]}")

print("\n=== knowledge-base tree (the 7 pages) ===")
status, payload = get(f"/{BANK}/knowledge-base/tree")
print(f"  {status}: {json.dumps(payload)[:700]}")
