## Done

- DLMM decode + quote, checked to 0 lamports against the program's `swapQuote` — variable fee ramp and limit orders, both swap directions.
- A reproducible diff harness (`validation/`) so anyone can confirm the match.

## Planned

**M1 — Production release.** Publish to PyPI, add CI, and widen the validation past a single pool to more pairs and bin steps.

**M2 — TypeScript / Rust port.** The same validated math as a droppable npm package or a Rust crate, so the TS/Rust bots and indexers can use it directly. 

**M3 — Web pool inspector.** Paste a pool address, see the decoded bins and a live quote.
Public, no install — a way for LPs and builders to use the engine without writing code.

**M4 (maybe) — more venues / exact-out.** CPMM (Raydium/Orca) through the same harness.

Ordering and timing may shift as I go.
