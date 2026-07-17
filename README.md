# meteora-dlmm-py

A Python library that prices Meteora DLMM swaps exactly — down to the lamport.

Give it a pool's on-chain account bytes and it returns the same `amount_out` the Meteora
program would: the bin-by-bin walk, the fee that ramps as a swap crosses bins, and the
on-chain limit orders from Meteora's December 2025 DLMM upgrade. Every number is checked
against the program's own `swapQuote`, and that check ships in this repo so you can run it
yourself, with no RPC key.

```
          in_raw          sdk_out          lib_out     diff   bins     fill
      1000000000         79109650         79109650        0      2     full
     10000000000        790983110        790983110        0      4     full
    100000000000       7901542802       7901542802        0     20     full
   1000000000000      58859103727      58859103727        0   3236      77%

max |diff| = 0 lamports over 4 sizes  ->  PASS: library == on-chain program.
```

That last row is a **partial fill** — the swap drains every BinArray in the capture and stops
at the window edge. The SDK, given the same window, stops in the same place, so `diff = 0` is
a real match — but it is agreement on a truncated window, not proof that a swap that size
prices correctly on-chain. The harness labels it rather than quietly counting it as a win.
See [Accuracy](#accuracy) for exactly what has and hasn't been validated.

## Why

- **It's Python.** Most Solana DLMM tooling is TypeScript or Rust. If you work in Python —
  quant research, backtests, data pipelines — this fills the gap.
- **One fetch, then local.** Decode a pool once from raw account bytes, then price as many
  swaps as you want in-process, with no further RPC round-trips. Useful for routing,
  liquidation math, backtests, and dashboards.
- **You can check it.** An independent implementation that matches the on-chain program
  exactly, with the diff harness committed so you can prove it without a key.

## Install

The library has no third-party dependencies, so installing it is quick:

```bash
git clone https://github.com/nirkt/meteora-dlmm-py.git && cd meteora-dlmm-py
pip install -e .          # or just add the folder to your PYTHONPATH
```

The library and examples are pure standard library. Only the validation harness in
`validation/` needs extra tools — see its setup below.

## Quickstart

```python
from meteora_dlmm import PoolState, quote

# bytes from getAccountInfo(pool) and getMultipleAccounts(bin_arrays)
pool = PoolState.from_accounts(lb_pair_bytes, bin_array_byte_list, decimals_x=9, decimals_y=6)

result = quote(pool, amount_in=1_000_000_000, swap_for_y=True)   # sell 1 SOL (X) for USDC (Y)
print(result.amount_out, result.bins_crossed)
```

`swap_for_y=True` spends token X (price falls); `False` spends token Y (price rises).
`quote()` also takes an optional `timestamp` (unix seconds) for the fee's decay reference,
and defaults to now.

### You must fetch enough BinArrays

`quote()` only knows about the bins you hand it. If a swap is big enough to walk past the last
BinArray you fetched, the honest answer is "I don't know" — not a smaller number. So it raises:

```python
from meteora_dlmm import quote, InsufficientBinArrays, array_index_of

try:
    result = quote(pool, amount_in, swap_for_y=True)
except InsufficientBinArrays as e:
    # e.bin_id         - the first bin we couldn't see
    # e.remaining_in   - input still unfilled
    # e.partial        - the Quote we got before running out (amount_out is a LOWER BOUND)
    fetch_more(array_index_of(e.bin_id))   # then re-quote
```

If you'd rather have the partial than an exception, pass `strict=False` and check the result:

```python
result = quote(pool, amount_in, swap_for_y=True, strict=False)
if not result.complete:
    print(f"lower bound only; {result.remaining_in} unfilled, need bin {result.missing_bin_id}")
```

If you fetched **every** BinArray the pool has — `getProgramAccounts` does this, and arrays only
exist where liquidity was placed — then there is no window to run off the end of, and a swap that
runs short means the pool is genuinely drained. Say so, and `quote()` will stop raising:

```python
pool = PoolState.from_accounts(lb_pair, all_bin_arrays, 9, 6, exhaustive=True)
result = quote(pool, huge_amount, swap_for_y=True)
# result.complete == True and result.remaining_in > 0  ->  pool drained; this fill is exact
```

Read the two fields together:

| `complete` | `remaining_in` | Meaning |
|-----------|----------------|---------|
| `True` | `0` | Full fill. `amount_out` is exact. |
| `True` | `> 0` | Pool drained. `amount_out` is exact — it's all the pool had. |
| `False` | `> 0` | We ran out of *data*, not liquidity. `amount_out` is a **lower bound**. Fetch more and re-quote. |

`examples/quote_minimal.py` is the shape to copy into your own code.
`examples/quote_from_rpc.py` fetches a live pool by address and quotes it.

## Verify it yourself

The `validation/` folder diffs this library against the SDK's `swapQuote`. Every script and
its options are documented in [validation/README.md](validation/README.md); here's the short
version.

The quick way needs no RPC and no key. `reference.json` is committed (it holds only public
on-chain data), so:

```bash
python3 validation/check_quote.py       # diff vs the SDK's swapQuote
python3 validation/check_token2022.py   # transfer-fee math + refusal of unquotable mints
python3 validation/live_check.py        # score vs real executed swaps
```

To capture fresh data from your own pool, you need a Solana RPC key (a free Helius key works
— sign up at https://helius.dev) and Node 20 LTS:

```bash
cd validation && npm install
export RPC_URL="https://mainnet.helius-rpc.com/?api-key=YOUR_KEY"
export POOL="<lbPair address>"
npx tsx capture_reference.mjs        # writes reference.json
python3 check_quote.py
```

Your key goes in `RPC_URL`. Raise `COUNT` (BinArrays fetched, default 8) until the largest
swap reports `full` rather than a percentage — otherwise you're comparing truncated windows.
Use `npx tsx find_pools.mjs` to list live pools.

## API

- `PoolState.from_accounts(lb_pair, bin_arrays, decimals_x, decimals_y, lb_pair_key=None,
  exhaustive=False)` — decode a pool from raw bytes. Pass `lb_pair_key` (32 bytes) to assert the
  BinArrays really belong to that pool. Pass `exhaustive=True` if `bin_arrays` is every array the
  pool has, so a short fill is reported as a drained pool rather than raising.
- `quote(pool, amount_in, swap_for_y, timestamp=None, support_limit_order=True, strict=True,
  fee_in=None, fee_out=None)`
  → `Quote(amount_out, bins_crossed, complete, remaining_in, missing_bin_id,
  transfer_fee_in, transfer_fee_out, gross_amount_out)`.
  Raises `InsufficientBinArrays` when `strict` and the walk leaves the loaded bin window.
  `fee_in`/`fee_out` are optional `TransferFee` objects for Token-2022 transfer-fee pools;
  omit them for standard SPL pools and behavior is unchanged.
- `quote_with_mints(pool, amount_in, swap_for_y, mint_x_info, mint_y_info, ...)` — convenience
  wrapper that resolves each side's transfer fee from decoded mint info and calls `quote()`.
- `parse_mint(mint_bytes, owner)` → `MintInfo(decimals, is_token_2022, transfer_fee,
  extensions)`. Decodes a mint's Token-2022 extensions. Raises `UnsupportedMint` (with the
  offending extension id) for transfer hooks and other transfer-altering extensions this
  library can't model off-chain — an honest refusal instead of a wrong number.
- `TransferFee(basis_points, max_fee)` with `.fee_on(amount)` — the on-chain `calculate_fee`
  (ceil, capped at `max_fee`).
- `PoolState.is_loaded(bin_id)`, `PoolState.loaded_bin_range()`, `array_index_of(bin_id)`
  — which bins you actually hold.
- `decode_lb_pair(bytes)` → `(static, variable, active_id, bin_step, mint_x, mint_y)`;
  `decode_bin_arrays(bytes_list)` → `(bins, loaded_array_indices)` — lower-level decoders.
- `DecodeError` on malformed or mismatched accounts.

## Accuracy

What the committed fixtures let you verify, with no key, right now:

| Check | Pool | Coverage | Result |
|-------|------|----------|--------|
| vs SDK `swapQuote` (`check_quote.py`) | 1bp SOL/USDC | X→Y, full fills across 1–20 bins, volatility accumulator nonzero so the fee ramp is live | **0 lamports** |
| vs real executed swaps (`live_check.py`) | same pool | 10 clean swaps, both directions | **median 0.0001%**, max 0.001% |
| Token-2022 fees + refusals (`check_token2022.py`) | reference pool + synthetic mints | transfer-fee math, cap, and every refusal path | **12/12 pass** |

What is **not** yet backed by a committed fixture, and shouldn't be taken on trust:

- Other bin steps and other pairs. The math doesn't depend on bin step, so they *should*
  pass — but "should" isn't "did".
- The Y→X direction against `swapQuote` (real executed swaps cover both directions; the
  `swapQuote` fixture is X→Y only).
- **Limit orders.** The committed pool has limit orders in only 2 of 3264 liquid bins, and the
  only swap that reaches them is the partial-fill one. The `processed_order` tier is never
  exercised. The three-tier fill was developed and matched against a 4bp limit-order pool
  during development, but that capture is not in this repo, so you can't check it here.

**Token-2022:** transfer-fee pools are priced exactly (the fee is applied as an outer layer,
verified by `check_token2022.py`). Pools whose tokens use a transfer *hook* or other
transfer-altering extension — e.g. MU/USDC — are **refused** with `UnsupportedMint` rather than
mis-quoted, because a hook's effect can't be computed off-chain. See
[LIMITATIONS.md](LIMITATIONS.md).

Widening the fixtures to many pools and bin steps is [M1 on the roadmap](ROADMAP.md).

[LIMITATIONS.md](LIMITATIONS.md) covers scope, assumptions, and the bugs I hit getting to an
exact match. [CHANGELOG.md](CHANGELOG.md) covers the changes in each release (0.4.0 added Token-2022 support).

## License

MIT.
