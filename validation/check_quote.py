#!/usr/bin/env python3
"""Diff the meteora_dlmm library against the SDK's swapQuote.

It checks two things: that the standalone decoder reads the same pool params the SDK
does, and that quote() matches swapQuote to the lamport across sizes. Reads reference.json
(from capture_reference.mjs) — no RPC or key needed here.

    python3 check_quote.py
"""
import base64
import json
import os

from meteora_dlmm import PoolState, quote
from meteora_dlmm.decode import decode_lb_pair, decode_bin_arrays

if not os.path.exists("reference.json"):
    raise SystemExit(
        "No reference.json here. Either use the one committed with the repo, or capture a\n"
        "fresh one:  RPC_URL=... POOL=... npx tsx capture_reference.mjs"
    )
d = json.load(open("reference.json"))
lb_pair = base64.b64decode(d["lbPairB64"])
bin_arrays = [base64.b64decode(b["data"]) for b in d["binArraysB64"]]

# 1) standalone decode vs SDK-decoded params
sp, vp, active_id, bin_step = decode_lb_pair(lb_pair)
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
print(f"\nquote vs swapQuote  (dir={'X->Y' if swap_for_y else 'Y->X'}, active={pool.active_id}, "
      f"binStep={pool.bin_step}bp, volAcc={vp.volatility_accumulator})")
print(f"{'in_raw':>16} {'sdk_out':>16} {'lib_out':>16} {'diff':>10} {'bins':>5}")
worst = 0
for r in d["results"]:
    if "error" in r:
        print(f"{r['inAmount']:>16}  SDK error: {r['error']}")
        continue
    in_amt, sdk_out = int(r["inAmount"]), int(r["outAmount"])
    res = quote(pool, in_amt, swap_for_y=swap_for_y, timestamp=ts)
    diff = res.amount_out - sdk_out
    worst = max(worst, abs(diff))
    print(f"{in_amt:>16} {sdk_out:>16} {res.amount_out:>16} {diff:>10} {res.bins_crossed:>5}")

print(f"\nmax |diff| = {worst} lamports  ->  " +
      ("PASS: library == on-chain program." if worst == 0 else "residual — investigate."))
