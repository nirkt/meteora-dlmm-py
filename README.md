# meteora-dlmm-py

A Python library that prices Meteora DLMM swaps exactly — down to the lamport.

Give it a pool's on-chain account bytes and it returns the same `amount_out` the Meteora
program would: the bin-by-bin walk, the fee that ramps as a swap crosses bins, and the
on-chain limit orders from Meteora's December 2025 DLMM upgrade. Every number is checked
against the program's own `swapQuote`, and that check ships in this repo so you can run it.

```
in_raw            sdk_out           lib_out          diff   bins
2000000000000     164139552586      164139552586        0      7
5000000000000     409532378565      409532378565        0     15
10000000000000    816406168505      816406168505        0     31
max |diff| = 0 lamports
```

## Why

- **It's Python.** Most Solana DLMM tooling is TypeScript or Rust. If you work in Python —
  quant research, backtests, data pipelines — this fills the gap.
- **No RPC round-trips.** Decode a pool once, then price as many swaps as you want,
  in-process. Useful for routing, liquidation math, backtests, and dashboards.
- **You can check it.** An independent implementation that matches the on-chain program
  exactly, limit orders included, with the diff harness to prove it.

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

`examples/quote_minimal.py` is the shape to copy into your own code.
`examples/quote_from_rpc.py` fetches a live pool by address and quotes it.

## Verify it yourself

The `validation/` folder diffs this library against the SDK's `swapQuote`. Every script and
its options are documented in [validation/README.md](validation/README.md); here's the short
version.

The quick way needs no RPC and no key. If a `reference.json` is committed (it holds only
public on-chain data), just run:

```bash
python3 validation/check_quote.py
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

Your key goes in `RPC_URL`.
Use `npx tsx find_pools.mjs` to list live pools, and pick a small bin step (1–4 bp) so swaps
cross several bins.

## API

- `PoolState.from_accounts(lb_pair, bin_arrays, decimals_x, decimals_y)` — decode a pool from raw bytes.
- `quote(pool, amount_in, swap_for_y, timestamp=None) -> Quote(amount_out, bins_crossed)`.
- `decode_lb_pair(bytes)`, `decode_bin_arrays(bytes_list, bin_step)` — lower-level decoders.

## Accuracy

| Venue | Status | Error vs on-chain |
|-------|--------|-------------------|
| Meteora DLMM — variable fee + limit orders, both directions | Validated | 0 lamports, 1–495 bins |

[LIMITATIONS.md](LIMITATIONS.md) covers scope, assumptions, and the bugs I hit getting to an
exact match. [ROADMAP.md](ROADMAP.md) covers what's next.

## License

MIT.
