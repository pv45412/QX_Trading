"""Scratch: prove F18 end-to-end on sectors that genuinely overlap.

XLK and SMH share NVDA/AVGO/AMD etc. Build a targeted snapshot into a TEMP path so
the live snapshot is untouched, then verify a name is findable under BOTH parents.
"""
import os
import sys
import tempfile

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import qx.explorer.ideas as ideas  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    original = ideas.SNAPSHOT_PATH
    ideas.SNAPSHOT_PATH = os.path.join(tmp, "snap.json")
    try:
        print("building a targeted snapshot for XLK + SMH (overlapping members)...")
        result = ideas.build(force=True, sectors=["XLK", "SMH"])
        print("  build:", result)

        data = ideas.ideas(view="all", limit=500)
        multi = [c for c in data["ideas"] if (c.get("membership_count") or 1) > 1]
        print(f"  candidates      : {data['row_count']}")
        print(f"  multi-membership: {len(multi)}")
        print(f"  policy          : {data.get('primary_parent_policy')}")
        print()

        for cand in multi[:6]:
            print(f"  {cand['symbol']:<6} primary={cand['sector_symbol']:<4} "
                  f"all={cand['sector_symbols']} "
                  f"memberships={[(m['sector_symbol'], m.get('weight')) for m in cand['memberships']]}")

        if multi:
            sample = multi[0]
            others = [s for s in sample["sector_symbols"] if s != sample["sector_symbol"]]
            print()
            for other in others:
                filtered = ideas.ideas(view="all", sector=other, limit=500)
                found = any(c["symbol"] == sample["symbol"] for c in filtered["ideas"])
                print(f"  filter sector={other}: finds {sample['symbol']} -> {found} "
                      f"({filtered['row_count']} rows)")
            primary_filtered = ideas.ideas(view="all", sector=sample["sector_symbol"], limit=500)
            print(f"  filter sector={sample['sector_symbol']} (primary): finds "
                  f"{sample['symbol']} -> "
                  f"{any(c['symbol'] == sample['symbol'] for c in primary_filtered['ideas'])}")
        else:
            print("  NO OVERLAP FOUND — cannot verify (unexpected for XLK+SMH)")
    finally:
        ideas.SNAPSHOT_PATH = original
