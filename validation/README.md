# Scripts

Every script in this folder, what it does, and how to run it. The project overview lives in
the [root README](../README.md); this is just the reference for the tooling.

The `.mjs` scripts need the Meteora JS SDK and Node 20 LTS:

```bash
npm install
```

Run them with `npx tsx` (plain `node` trips on the SDK's TypeScript imports). Put your RPC
URL in the environment — a free Helius key works (https://helius.dev). The Python scripts
read the files the `.mjs` scripts write, and need no RPC of their own.

## find_pools.mjs
Lists live SOL-USDC DLMM pools by 24h volume, so you can pick one to test against. Prefer a
small bin step (1–4 bp) — swaps then cross several bins, which is what actually exercises the
walk. No RPC needed (it reads Meteora's public pool API).

```bash
npx tsx find_pools.mjs
```

## capture_reference.mjs
Snapshots a pool and records the SDK's `swapQuote` output plus the raw account bytes into
`reference.json`, which `check_quote.py` then diffs against.

```bash
RPC_URL="https://mainnet.helius-rpc.com/?api-key=..." \
POOL="<lbPair address>" \
npx tsx capture_reference.mjs
```

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `RPC_URL` | yes | — | your Solana RPC endpoint |
| `POOL` | yes | — | the LbPair (pool) address |
| `SWAP_FOR_Y` | no | `true` | `true` = spend token X (sell); `false` = spend token Y (buy) |
| `AMOUNTS` | no | `0.1,1,5,20,50,100,200` | input sizes (UI units of the token being spent) |

## check_quote.py
Diffs the Python library against `reference.json`: first checks the standalone decoder reads
the same params the SDK does, then checks `quote()` matches `swapQuote` to the lamport. Needs
no RPC or key.

```bash
python3 check_quote.py
```

## live_capture.mjs
Optional forward test. Watches the pool for real executed swaps over a window and, for each
clean single-swap moment, records the pre-swap state + the executed amounts into
`live_events.jsonl`.

```bash
RPC_URL="https://mainnet.helius-rpc.com/?api-key=..." \
POOL="<lbPair address>" \
npx tsx live_capture.mjs
```

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `RPC_URL` | yes | — | your Solana RPC endpoint |
| `POOL` | yes | — | the LbPair (pool) address |
| `DURATION` | no | `3600` | how long to watch, in seconds |
| `INTERVAL` | no | `20` | seconds between snapshots |

## live_check.py
Scores the library's quotes against the real swaps captured in `live_events.jsonl`. Splits
events into clean vs rejected (dust / multi-hop routes / misparsed) and reports the error on
the clean ones.

```bash
python3 live_check.py
```

`REJECT_FRAC` (default `0.50`) and `MIN_IN_UI` (default `1e-4`) can tune the filters.
