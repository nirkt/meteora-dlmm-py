#!/usr/bin/env python3
"""Diff the meteora_dlmm library against the SDK's swapQuote.

It checks three things: that the standalone decoder reads the same pool params the SDK does,
that quote() matches swapQuote to the lamport across sizes, and that we are honest about
which of those comparisons are FULL fills versus partial fills bounded by the captured bin
window. Reads reference.json (from capture_reference.mjs) — no RPC or key needed here.

    python3 check_quote.py
"""
import base64
import json
import os

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meteora_dlmm import PoolState, quote
from meteora_dlmm.decode import decode_lb_pair

if not os.path.exists("reference.json"):
    raise SystemExit(
        "No reference.json here. Either use the one committed with the repo, or capture a\n"
        "fresh one:  RPC_URL=... POOL=... npx tsx capture_reference.mjs"
    )
d = json.load(open("reference.json"))
lb_pair = base64.b64decode(d["lbPairB64"])
bin_arrays = [base64.b64decode(b["data"]) for b in d["binArraysB64"]]

# 1) standalone decode vs SDK-decoded params
sp, vp, active_id, bin_step, mint_x, mint_y = decode_lb_pair(lb_pair)
sdk = d["sdk"]
checks = {
    "activeId": (active_id, sdk["activeId"]),
    "binStep": (bin_step, sdk["binStep"]),
    "baseFactor": (sp.base_factor, sdk["baseFactor"]),
    "variableFeeControl": (sp.variable_fee_control, sdk["variableFeeControl"]),
    "maxVolatilityAccumulator": (sp.max_volatility_accumulator, sdk["maxVolatilityAccumulator"]),
    "filterPeriod": (sp.filter_period, sdk["filterPeriod"]),
    "volatilityAccumulator": (vp.volatility_accumulator, sdk["volatilityAccumulator"]),
    "indexReference": (vp.index_reference, sdk["indexReference"]),
}
print("standalone LbPair decode vs SDK:")
decode_ok = True
for name, (got, want) in checks.items():
    ok = got == want
    decode_ok &= ok
    print(f"  {name:<26} {got:<14} {'OK' if ok else f'!= {want}  <-- OFFSET MISMATCH'}")
if not decode_ok:
    raise SystemExit("LbPair decode disagrees with the SDK — fix offsets before trusting quotes.")

# 2) quote() vs swapQuote
pool = PoolState.from_accounts(lb_pair, bin_arrays, d["decX"], d["decY"])
swap_for_y = d["swapForY"]
ts = d["clockTs"]
lo, hi = pool.loaded_bin_range()
print(f"\nquote vs swapQuote  (dir={'X->Y' if swap_for_y else 'Y->X'}, active={pool.active_id}, "
      f"binStep={pool.bin_step}bp, volAcc={vp.volatility_accumulator})")
print(f"captured bin window: {len(pool.loaded_arrays)} BinArrays, bins {lo}..{hi}")
print(f"{'in_raw':>16} {'sdk_out':>16} {'lib_out':>16} {'diff':>8} {'bins':>6} {'fill':>8}")
worst = 0
partial = 0
for r in d["results"]:
    if "error" in r:
        print(f"{r['inAmount']:>16}  SDK error: {r['error']}")
        continue
    in_amt, sdk_out = int(r["inAmount"]), int(r["outAmount"])
    # strict=False: the SDK was called with partial-fill enabled and the SAME bin window,
    # so an apples-to-apples diff means letting our walk stop at that window too.
    res = quote(pool, in_amt, swap_for_y=swap_for_y, timestamp=ts, strict=False)
    diff = res.amount_out - sdk_out
    worst = max(worst, abs(diff))
    if res.complete:
        fill = "full"
    else:
        partial += 1
        fill = f"{100 * (1 - res.remaining_in / in_amt):.0f}%"
    print(f"{in_amt:>16} {sdk_out:>16} {res.amount_out:>16} {diff:>8} {res.bins_crossed:>6} {fill:>8}")

print(f"\nmax |diff| = {worst} lamports over {len(d['results'])} sizes  ->  " +
      ("PASS: library == on-chain program." if worst == 0 else "residual — investigate."))
if partial:
    print(
        f"\nNOTE: {partial} of these are PARTIAL fills — the swap drained every BinArray in the\n"
        f"capture and stopped at the window edge. The SDK (called with partial-fill on, over the\n"
        f"same window) stopped in the same place, so diff=0 is still a real apples-to-apples\n"
        f"match — but it is agreement on a truncated window, NOT proof that a swap this size\n"
        f"quotes correctly on-chain. Recapture with a bigger COUNT to make these full fills:\n"
        f"    RPC_URL=... POOL={d['pool']} COUNT=96 npx tsx capture_reference.mjs"
    )
