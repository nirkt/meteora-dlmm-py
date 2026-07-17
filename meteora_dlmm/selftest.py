"""Reproduce the lamport-exact claim from an installed copy.

    python -m meteora_dlmm.selftest

Loads the committed reference capture (a real 1bp SOL/USDC pool with four swapQuote outputs
recorded from the on-chain program) and checks this library reproduces every one to the
lamport. Exits non-zero on any mismatch, so it doubles as a CI smoke test.
"""
from __future__ import annotations

import base64
import json
import sys
from importlib import resources

from . import PoolState, quote


def _load_fixture() -> dict:
    try:
        with resources.files("meteora_dlmm").joinpath("_reference.json").open() as f:
            return json.load(f)
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "validation" / "reference.json"
        with p.open() as f:
            return json.load(f)


def main() -> int:
    d = _load_fixture()
    lb = base64.b64decode(d["lbPairB64"])
    arrays = [base64.b64decode(b["data"]) for b in d["binArraysB64"]]
    pool = PoolState.from_accounts(lb, arrays, d["decX"], d["decY"])
    ts = float(d["clockTs"])
    swap_for_y = bool(d["swapForY"])

    worst = 0
    print(f"{'in':>16}  {'sdk_out':>14}  {'lib_out':>14}  {'diff':>6}")
    for r in d["results"]:
        q = quote(pool, int(r["inAmount"]), swap_for_y, timestamp=ts, strict=False)
        diff = q.amount_out - int(r["outAmount"])
        worst = max(worst, abs(diff))
        print(f"{r['inAmount']:>16}  {r['outAmount']:>14}  {q.amount_out:>14}  {diff:>6}")

    print(f"\nmax |diff| = {worst} lamports", end="  ->  ")
    if worst == 0:
        print("PASS: library reproduces the on-chain program exactly.")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
