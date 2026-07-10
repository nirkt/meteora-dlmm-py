#!/usr/bin/env python3
"""Score library quotes against REAL executed swaps captured by live_capture.mjs.

Each event is priced with the full fee ramp using that swap's own pre-snapshot
pool state. Events are split into CLEAN vs REJECTED (dust / degenerate / price
outliers = multi-hop routes or misparsed vault deltas) so the error table reflects
the library, not the capture parser.

    python3 live_check.py         # reads live_events.jsonl
"""
import base64
import json
import os
import statistics

from meteora_dlmm import PoolState, quote
from meteora_dlmm.decode import decode_lb_pair, decode_bin_arrays

PATH = "live_events.jsonl"
REJECT_FRAC = float(os.environ.get("REJECT_FRAC", "0.50"))  # |implied/spot - 1| cutoff
MIN_IN_UI = float(os.environ.get("MIN_IN_UI", "1e-4"))

if not os.path.exists(PATH):
    raise SystemExit("no live_events.jsonl yet — run live_capture.mjs first")

clean, rejected = [], []
for line in open(PATH):
    line = line.strip()
    if not line:
        continue
    e = json.loads(line)
    lb = base64.b64decode(e["lbPairB64"])
    sp, vp, active_id, bin_step = decode_lb_pair(lb)
    bins = decode_bin_arrays([base64.b64decode(b["data"]) for b in e["preBinArraysB64"]], bin_step)
    pool = PoolState(active_id, bin_step, e["decX"], e["decY"], sp, vp, bins)

    sfy = e["swapForY"]
    in_dec, out_dec = (e["decX"], e["decY"]) if sfy else (e["decY"], e["decX"])
    amt_in, executed = int(e["amountIn"]), int(e["amountOut"])
    in_ui = amt_in / 10 ** in_dec
    if in_ui < MIN_IN_UI:
        rejected.append("dust"); continue
    if executed <= 0:
        rejected.append("degenerate"); continue
    spot, out_ui = pool.spot_price(), executed / 10 ** out_dec
    implied = (out_ui / in_ui) if sfy else (in_ui / out_ui)
    if spot > 0 and out_ui > 0 and abs(implied / spot - 1) > REJECT_FRAC:
        rejected.append("price_outlier"); continue

    predicted = quote(pool, amt_in, swap_for_y=sfy).amount_out
    rel = (predicted - executed) / executed * 100 if executed else 0.0
    clean.append((sfy, amt_in, executed, predicted, rel))

if clean:
    print(f"{'dir':>4} {'in_raw':>16} {'executed':>16} {'predicted':>16} {'rel%':>10}")
    for sfy, i, ex, pr, rel in clean:
        print(f"{'X->Y' if sfy else 'Y->X':>4} {i:>16} {ex:>16} {pr:>16} {rel:>9.4f}%")
    errs = sorted(abs(r[4]) for r in clean)
    print(f"\nCLEAN n={len(clean)}  median|rel|={statistics.median(errs):.4f}%  "
          f"p90={errs[min(len(errs) - 1, int(len(errs) * 0.9))]:.3f}%  max={max(errs):.3f}%")
    print("  tail = pre-snapshot staleness (tighten INTERVAL / use onAccountChange), not the math.")
if rejected:
    from collections import Counter
    print(f"REJECTED n={len(rejected)}  " + "  ".join(f"{k}={v}" for k, v in Counter(rejected).items()))
