"""Phase E regression tests — F19: atomic persistence, job claiming, corruption.

Reviewer F19: snapshot and order JSON writes were direct rather than atomic; read
errors became "no snapshot" or an empty order list, masking corruption; and
build_async checked the running flag outside the lock, so two builds could overlap.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

passed = failed = 0
results: list[dict] = []


def check(fid, title, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {fid}  {title}")
    else:
        failed += 1
        print(f"  FAIL  {fid}  {title}  {detail}")
    results.append({"finding": fid, "title": title, "ok": bool(condition), "detail": str(detail)})


from qx.core.atomic_store import (  # noqa: E402
    STATUS_CORRUPT,
    STATUS_MISSING,
    STATUS_OK,
    JobClaim,
    atomic_write_json,
    quarantine,
    read_json,
)

print("== atomic writes ==")
with tempfile.TemporaryDirectory() as tmp:
    target = os.path.join(tmp, "store.json")

    # A reader must never observe a partial file.
    atomic_write_json(target, {"a": 1})
    check("E1", "a written file reads back intact",
          read_json(target).payload == {"a": 1}, read_json(target).payload)

    # Overwriting must not truncate-then-write: the old content stays readable until
    # the swap. Simulate a crash mid-write by making the dump raise.
    class Boom(Exception):
        pass

    original_dump = json.dump
    try:
        def exploding_dump(obj, fp, **kw):
            fp.write('{"partial": ')
            raise Boom("simulated crash mid-write")
        json.dump = exploding_dump
        try:
            atomic_write_json(target, {"b": 2})
        except Boom:
            pass
    finally:
        json.dump = original_dump

    after = read_json(target)
    check("E2", "a crashed write leaves the PREVIOUS content intact",
          after.status == STATUS_OK and after.payload == {"a": 1},
          f"status={after.status} payload={after.payload}")

    leftovers = [n for n in os.listdir(tmp) if n.startswith(".tmp-")]
    check("E3", "a crashed write leaves no temp file behind", not leftovers, leftovers)

    # No stray temp files after a normal write either.
    atomic_write_json(target, {"c": 3})
    leftovers = [n for n in os.listdir(tmp) if n.startswith(".tmp-")]
    check("E4", "a normal write leaves no temp file behind", not leftovers, leftovers)
    check("E5", "the new content is what a reader sees",
          read_json(target).payload == {"c": 3}, read_json(target).payload)

print("\n== corruption is distinguished from absence ==")
with tempfile.TemporaryDirectory() as tmp:
    missing = os.path.join(tmp, "nope.json")
    check("E6", "a missing file reports MISSING",
          read_json(missing).status == STATUS_MISSING, read_json(missing).status)

    corrupt = os.path.join(tmp, "bad.json")
    Path(corrupt).write_text('{"broken": ', encoding="utf-8")
    result = read_json(corrupt)
    check("E7", "a truncated file reports CORRUPT, not MISSING",
          result.status == STATUS_CORRUPT, result.status)
    check("E8", "the corruption carries a reason",
          bool(result.error), result.error)
    check("E9", "corrupt is not confused with ok",
          result.corrupt and not result.ok)

    empty = os.path.join(tmp, "empty.json")
    Path(empty).write_text("", encoding="utf-8")
    check("E10", "an empty file reports CORRUPT", read_json(empty).status == STATUS_CORRUPT,
          read_json(empty).status)

    # Binary junk.
    junk = os.path.join(tmp, "junk.json")
    Path(junk).write_bytes(b"\xff\xfe\x00\x01binary")
    check("E11", "binary junk reports CORRUPT", read_json(junk).status == STATUS_CORRUPT,
          read_json(junk).status)

    # Valid JSON of the wrong shape is still OK at this layer; callers type-check.
    wrong = os.path.join(tmp, "wrong.json")
    Path(wrong).write_text('"just a string"', encoding="utf-8")
    check("E12", "valid JSON of an unexpected shape reads OK at this layer",
          read_json(wrong).status == STATUS_OK, read_json(wrong).status)

print("\n== quarantine preserves evidence ==")
with tempfile.TemporaryDirectory() as tmp:
    corrupt = os.path.join(tmp, "orders.json")
    Path(corrupt).write_text("{bad", encoding="utf-8")
    moved = quarantine(corrupt)
    check("E13", "quarantine moves the file aside", moved is not None and os.path.exists(moved),
          moved)
    check("E14", "the original path is now free", not os.path.exists(corrupt))
    check("E15", "the quarantined file still holds the evidence",
          moved is not None and "bad" in Path(moved).read_text(encoding="utf-8"))
    check("E16", "quarantining a missing file is a no-op", quarantine(corrupt) is None)

print("\n== job claiming is atomic ==")
claim = JobClaim(("started_at", "done", "total", "current", "error"))
check("E17", "the first claim succeeds", claim.claim(done=0, total=5) is True)
check("E18", "a second claim is refused", claim.claim(done=0, total=5) is False)
check("E19", "state is visible while running", claim.snapshot()["running"] is True)
claim.release(error=None)
check("E20", "release frees the job", claim.claim(done=0) is True)

# The real race: N threads calling claim() at once, exactly one must win.
for attempt in range(3):
    fresh = JobClaim(("done",))
    winners: list[int] = []
    barrier = threading.Barrier(12)

    def worker(index):
        barrier.wait()
        if fresh.claim(done=0):
            winners.append(index)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check(f"E21-{attempt}", "exactly one of 12 concurrent claims wins",
          len(winners) == 1, f"winners={winners}")

print("\n== concurrent increments are not lost ==")
counter = JobClaim(("done",))
counter.claim(done=0)
threads = [threading.Thread(target=lambda: [counter.increment("done") for _ in range(200)])
           for _ in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("E22", "1600 concurrent increments all land",
      counter.snapshot()["done"] == 1600, counter.snapshot()["done"])

print("\n== the real stores now behave ==")
import qx.explorer.ideas as ideas  # noqa: E402
import qx.app.trade as trade  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    original = ideas.SNAPSHOT_PATH
    ideas.SNAPSHOT_PATH = os.path.join(tmp, "snap.json")
    try:
        check("E23", "no snapshot yet reports MISSING via the reader",
              ideas._read_snapshot_result().status == STATUS_MISSING,
              ideas._read_snapshot_result().status)
        ideas._write_snapshot({"generated_at": "2026-10-13T00:00:00+00:00", "candidates": []})
        check("E24", "a written snapshot reads back",
              ideas._read_snapshot_result().status == STATUS_OK)
        Path(ideas.SNAPSHOT_PATH).write_text("{corrupt", encoding="utf-8")
        check("E25", "a corrupt snapshot is reported as CORRUPT",
              ideas._read_snapshot_result().status == STATUS_CORRUPT,
              ideas._read_snapshot_result().status)
        status = ideas.status()
        check("E26", "status surfaces the corruption",
              status.get("snapshot_status") == STATUS_CORRUPT, status.get("snapshot_status"))
        check("E27", "status does not claim a snapshot exists when corrupt",
              status.get("has_snapshot") is False, status.get("has_snapshot"))
    finally:
        ideas.SNAPSHOT_PATH = original

with tempfile.TemporaryDirectory() as tmp:
    original = trade.ORDER_STORE
    trade.ORDER_STORE = os.path.join(tmp, "orders.json")
    try:
        check("E28", "an absent order store reports MISSING",
              trade._load_orders_result().status == STATUS_MISSING)
        trade._save_orders([{"intent_id": "X"}])
        check("E29", "a saved order list reads back",
              trade._load_orders_result().status == STATUS_OK)
        Path(trade.ORDER_STORE).write_text("[]]", encoding="utf-8")
        check("E30", "a corrupt order store is reported as CORRUPT",
              trade._load_orders_result().status == STATUS_CORRUPT,
              trade._load_orders_result().status)
        listed = trade.list_orders()
        check("E31", "list_orders surfaces the corruption",
              listed.get("store_status") == STATUS_CORRUPT, listed.get("store_status"))
    finally:
        trade.ORDER_STORE = original

print("\n== SAFETY: a corrupt ledger must not be written over ==")
import types  # noqa: E402

stub = types.ModuleType("qx.reporting.schwab_activity")
stub.SchwabActivityReader = object
sys.modules.setdefault("qx.reporting.schwab_activity", stub)
import qx.app.trade as trade_mod  # noqa: E402

trade_mod._quote = lambda s: {"last": 100, "source": "schwab", "realtime": True,
                              "timestamp": "2026-10-13T12:00:00+00:00"}
trade_mod.account_detail = lambda a: {"balances": {"equity": 100000, "buying_power": 100000},
                                      "positions": []}

with tempfile.TemporaryDirectory() as tmp:
    original = trade_mod.ORDER_STORE
    trade_mod.ORDER_STORE = os.path.join(tmp, "orders.json")
    try:
        ticket = {"symbol": "XYZ", "side": "BUY", "quantity": 1, "order_type": "MARKET"}
        first = trade_mod.submit_simulated(ticket, account_number="T", confirm=True)
        check("E32", "a valid submission succeeds on a clean ledger",
              first.get("ok") is True, json.dumps(first)[:90])

        # Corrupt the ledger, then try to submit again.
        Path(trade_mod.ORDER_STORE).write_text("{not json", encoding="utf-8")
        blocked = trade_mod.submit_simulated(ticket, account_number="T", confirm=True)
        check("E33", "submission is REFUSED when the ledger is unreadable",
              blocked.get("ok") is False, json.dumps(blocked)[:110])
        check("E34", "the refusal names the store condition",
              blocked.get("store_status") == STATUS_CORRUPT, blocked.get("store_status"))
        check("E35", "the refusal explains why (duplicate suppression unverifiable)",
              "duplicate" in str(blocked.get("error", "")).lower(),
              str(blocked.get("error"))[:90])
        quarantined = blocked.get("quarantined_to")
        check("E36", "the corrupt ledger is quarantined, not overwritten",
              bool(quarantined) and os.path.exists(quarantined), quarantined)
        check("E37", "the quarantined file still holds the original evidence",
              quarantined is not None and "{not json" in Path(quarantined).read_text(encoding="utf-8"))

        # With the corrupt file moved aside the path is free, so a fresh submit works.
        after = trade_mod.submit_simulated(ticket, account_number="T", confirm=True)
        check("E38", "a fresh submission works once the damaged file is set aside",
              after.get("ok") is True, json.dumps(after)[:90])
    finally:
        trade_mod.ORDER_STORE = original

print("\n== SAFETY: concurrent builds cannot overlap ==")
with tempfile.TemporaryDirectory() as tmp:
    original = ideas.SNAPSHOT_PATH
    ideas.SNAPSHOT_PATH = os.path.join(tmp, "snap.json")
    try:
        # Hold the claim, then confirm both entry points refuse.
        ideas._BUILDING.claim(started_at="t", done=0, total=0, current="HELD", error=None)
        blocked_async = ideas.build_async()
        check("E39", "build_async refuses while a build is claimed",
              blocked_async.get("ok") is False, json.dumps(blocked_async)[:90])
        blocked_sync = ideas.build(sectors=["XLK"])
        check("E40", "build() refuses while a build is claimed",
              blocked_sync.get("ok") is False, json.dumps(blocked_sync)[:90])
        check("E41", "the refusal reports the current job state",
              blocked_async.get("building", {}).get("running") is True,
              blocked_async.get("building"))
        ideas._BUILDING.release()
        check("E42", "after release the claim is free again",
              ideas._BUILDING.snapshot()["running"] is False)
    finally:
        ideas._BUILDING.release()
        ideas.SNAPSHOT_PATH = original

Path(r"C:\Project\2026\scratch\phase_e_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print(f"\nRESULT: {passed} passed, {failed} failed")
