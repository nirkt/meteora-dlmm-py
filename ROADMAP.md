## Done

- DLMM decode + quote, checked to 0 lamports against the program's `swapQuote` — variable fee
  ramp and three-tier limit-order fill, bin-by-bin walk.
- A reproducible diff harness (`validation/`) so anyone can confirm the match with no RPC key.
- A forward test against real executed swaps (`live_check.py`), median error 0.0001%.
- Published to PyPI: `pip install meteora-dlmm`, with a bundled self-test.
- Token-2022 support: transfer fees priced exactly; transfer-hook and other transfer-altering
  extensions refused with `UnsupportedMint` rather than mis-quoted (`check_token2022.py`).
- Web pool inspector live at dlmm.dev — paste a pool, see decoded bins and a live quote beside
  the SDK's own answer.

Exactly what the committed fixtures do and don't demonstrate is spelled out in
[LIMITATIONS.md](LIMITATIONS.md) — the short version is that both are the same 1bp SOL/USDC
pool, so bin-step and pair coverage is the first gap to close.

## Planned

**M1 — Widen validation.** (PyPI publish: done.) The remaining piece is broad fixture
coverage — a sweep that captures many pools across pairs and bin steps, commits the fixtures,
and diffs them all offline in one command. This is what turns "should pass" into "did pass",
and it deliberately includes large-raw-price pools.

**M2 — TypeScript / Rust port.** The same validated math as a droppable npm package or a Rust
crate, so the TS/Rust bots and indexers can use it directly.

**M3 — Web pool inspector.** (Almost done, I need to fix some bugs and clean up the repo before publishing — live at dlmm.dev.) Paste a pool address, see the decoded
bins and a live quote beside the SDK's own answer. Public, no install.

**M4 (maybe) — more venues / exact-out.** CPMM (Raydium/Orca) through the same harness.

Ordering and timing may shift as I go.
