## Done

- DLMM decode + quote, checked to 0 lamports against the program's `swapQuote` — variable fee
  ramp and three-tier limit-order fill, bin-by-bin walk.
- A reproducible diff harness (`validation/`) so anyone can confirm the match with no RPC key.
- A forward test against real executed swaps (`live_check.py`), median error 0.0001%.

Exactly what the committed fixtures do and don't demonstrate is spelled out in
[LIMITATIONS.md](LIMITATIONS.md) — the short version is that both are the same 1bp SOL/USDC
pool, so bin-step and pair coverage is the first gap to close.

## Planned

**M1 — Production release.** Publish to PyPI, add CI, and widen validation past a single pool:
a sweep that captures many pools across pairs and bin steps, commits the fixtures, and diffs
them all offline in one command. This is what turns "should pass" into "did pass" — and it
deliberately includes pools whose raw price is large, since that's the case the 0.2.0 decode
fix targets.

**M2 — TypeScript / Rust port.** The same validated math as a droppable npm package or a Rust
crate, so the TS/Rust bots and indexers can use it directly.

**M3 — Web pool inspector.** Paste a pool address, see the decoded bins and a live quote,
side by side with the SDK's own answer. Public, no install — a way for LPs and builders to use
the engine without writing code.

**M4 (maybe) — more venues / exact-out.** CPMM (Raydium/Orca) through the same harness.

Ordering and timing may shift as I go.
