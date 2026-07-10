"""Fetch a live pool by address and quote a swap — standalone, stdlib only.

    RPC_URL="https://your-rpc/?api-key=..." \
    python3 quote_from_rpc.py <POOL_ADDRESS> [amount_ui] [x|y]

It pulls the pool's BinArrays with getProgramAccounts, a heavy call that some RPC providers
restrict — if yours does, use a provider that allows it, or fetch the bin-array bytes another
way and pass them to PoolState.from_accounts. Decimals default to SOL/USDC (9/6); pass your
own for a different pair.
"""
import base64
import json
import os
import sys
import urllib.request

from meteora_dlmm import PoolState, quote
from meteora_dlmm.constants import BIN_ARRAY_SIZE

RPC = os.environ.get("RPC_URL")
DLMM_PROGRAM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if resp.get("error"):
        sys.exit(f"RPC error on {method}: {resp['error']}")
    return resp["result"]


def main():
    if not RPC or len(sys.argv) < 2:
        sys.exit("set RPC_URL and pass a pool address")
    pool_addr = sys.argv[1]
    amount_ui = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    swap_for_y = (sys.argv[3].lower() != "y") if len(sys.argv) > 3 else True
    dec_x, dec_y = 9, 6

    account = rpc("getAccountInfo", [pool_addr, {"encoding": "base64"}])["value"]
    if account is None:
        sys.exit(f"pool not found: {pool_addr}  (pass just the address, not POOL=...)")
    lb_pair = base64.b64decode(account["data"][0])
    accounts = rpc("getProgramAccounts", [DLMM_PROGRAM, {
        "encoding": "base64",
        "filters": [{"memcmp": {"offset": 24, "bytes": pool_addr}}, {"dataSize": BIN_ARRAY_SIZE}],
    }])
    bin_arrays = [base64.b64decode(a["account"]["data"][0]) for a in accounts]

    pool = PoolState.from_accounts(lb_pair, bin_arrays, dec_x, dec_y)
    in_dec = dec_x if swap_for_y else dec_y
    out_dec = dec_y if swap_for_y else dec_x
    print(f"pool active={pool.active_id} bin_step={pool.bin_step}bp  spot=${pool.spot_price():,.2f}  "
          f"bins={len(pool.bins)}  dir={'X->Y' if swap_for_y else 'Y->X'}")

    for mult in (1, 10, 100, 1000):
        amt = int(amount_ui * mult * 10 ** in_dec)
        r = quote(pool, amt, swap_for_y=swap_for_y)
        print(f"  in={amount_ui*mult:<12g} out={r.amount_out / 10 ** out_dec:<16.6f} bins={r.bins_crossed}")


if __name__ == "__main__":
    main()
