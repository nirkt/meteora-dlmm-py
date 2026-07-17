"""Token-2022 regression: transfer-fee math, and refusal of unquotable mints.

Run:  python validation/check_token2022.py    (from the repo root)
Exits nonzero on any failure, so it doubles as a CI gate.
"""
import base64, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meteora_dlmm import PoolState, quote, TransferFee, parse_mint, UnsupportedMint
from meteora_dlmm.token2022 import TOKEN_PROGRAM, TOKEN_2022_PROGRAM

fails = 0
def check(name, cond):
    global fails
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    fails += not cond

d = json.load(open(Path(__file__).parent / "reference.json"))
pool = PoolState.from_accounts(
    base64.b64decode(d["lbPairB64"]),
    [base64.b64decode(b["data"]) for b in d["binArraysB64"]],
    d["decX"], d["decY"])
ts = float(d["clockTs"])
amt = 1_000_000_000

base = quote(pool, amt, True, timestamp=ts)
check("baseline unchanged (79109650)", base.amount_out == 79109650)

qin = quote(pool, amt, True, timestamp=ts, fee_in=TransferFee(100, 10**18))
check("1% input fee skims 10_000_000", qin.transfer_fee_in == 10_000_000)
check("input fee reduces output", qin.amount_out < base.amount_out)

qout = quote(pool, amt, True, timestamp=ts, fee_out=TransferFee(100, 10**18))
exp = (base.amount_out * 100 + 9999) // 10000
check("output fee: gross preserved", qout.gross_amount_out == base.amount_out)
check("output fee: correct amount", qout.transfer_fee_out == exp)
check("output fee: net = gross - fee", qout.amount_out == qout.gross_amount_out - qout.transfer_fee_out)

check("fee cap enforced", quote(pool, amt, True, timestamp=ts, fee_out=TransferFee(100, 5)).transfer_fee_out == 5)
check("zero-bps fee == baseline", quote(pool, amt, True, timestamp=ts, fee_in=TransferFee(0, 0)).amount_out == base.amount_out)

# --- refusal cases ---
def mint(decimals, exts, ver=TOKEN_2022_PROGRAM):
    b = bytearray(166); b[44] = decimals; b[165] = 1
    for t, body in exts:
        b += t.to_bytes(2, "little") + len(body).to_bytes(2, "little") + body
    return bytes(b), ver

classic = bytearray(82); classic[44] = 9
check("classic SPL is quotable", parse_mint(bytes(classic), TOKEN_PROGRAM).transfer_fee is None)

hook_body = bytes([9]) + bytes(63)  # nonzero hook program
data, owner = mint(6, [(14, hook_body)])
try:
    parse_mint(data, owner); check("real transfer hook refused", False)
except UnsupportedMint as e:
    check("real transfer hook refused", e.extension == 14)

data, owner = mint(6, [(14, bytes(64))])  # zero hook program = no-op
try:
    parse_mint(data, owner); check("no-op hook allowed", True)
except UnsupportedMint:
    check("no-op hook allowed", False)

data, owner = mint(6, [(9, b"")])  # NonTransferable
try:
    parse_mint(data, owner); check("non-transferable refused", False)
except UnsupportedMint:
    check("non-transferable refused", True)

print(f"\n{'PASS' if not fails else 'FAIL'}: token-2022 support ({fails} failures)")
sys.exit(1 if fails else 0)
