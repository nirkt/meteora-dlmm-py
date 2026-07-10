# Limitations & scope

What the library does, what it doesn't, and a few bugs I hit getting the numbers to match
the on-chain program exactly.

## What it covers

- **Meteora DLMM only.** No CPMM (Raydium/Orca) or Whirlpool CLMM here.
- **Exact-in swaps.** You give an input amount, it gives the output. No exact-out.
- **The current DLMM program** (with limit orders, from the Dec 2025 upgrade). The decoder
  reads that bin layout, checked against a live pool. For older or forked pools that use the
  classic bin layout, pass `support_limit_order=False` to `quote()` — otherwise it would
  read the limit-order offsets (+112/+128/+140) as unrelated bytes.

## Assumptions

- **No Token-2022 transfer fees.** The program strips any token transfer fee before
  swapping; the library assumes zero, which is true for SOL/USDC and most pairs. A pair with
  a transfer-fee extension would need that step added.
- **You provide the liquidity.** `quote()` only walks the bin arrays you pass in. If the
  input is bigger than that liquidity, it partial-fills (same as the SDK). Fetch enough bin
  arrays in the swap direction to cover large swaps.
- **Fee-decay timestamp.** The variable fee's decay depends on the current time. `quote()`
  uses "now" by default. To reproduce one specific past swap, pass that swap's block time —
  a sub-second gap from the program's clock can flip the decay branch right at the
  `filterPeriod` boundary. That's a rare one-off edge, not a systematic error.

## How far it's been validated

Matched to 0 lamports against the program's `swapQuote` on a live 4bp limit-order pool,
both directions, on swaps crossing 1 to 495 bins, with a nonzero volatility accumulator
(so the fee ramp is in play) and limit orders in roughly a quarter of the bins. Other bin
steps and pairs aren't tested yet — the math doesn't depend on bin step, so they should
pass, but "should" isn't "did".

## Bugs I hit on the way

Getting to `diff=0` meant fixing a few subtle bugs. Each one is a real DLMM gotcha worth
knowing about:

- **`bin.price` is a plain Q64.64 price, not a sqrt price.** An early version borrowed the
  Whirlpool/Uniswap `sqrtPriceX64` idea and squared it, which is off by a factor of the
  price on real data. DLMM stores `(1 + bin_step/1e4)^id` directly; the swap uses one shift.
- **A bin fills based on input, not output.** It caps when the input hits `maxAmountIn`
  (rounded up), not when the output hits the reserve. The two disagree at rounding
  boundaries — a few lamports per bin, invisible under ~4 bins, compounding past 7.
- **The variable fee ramps per bin.** The volatility accumulator grows with distance from
  the reference bin and caps at `maxVolatilityAccumulator`. A flat fee is only right for a
  single bin; multi-bin swaps need it recomputed each bin.
- **Bins fill in three tiers.** AMM reserve first, then processed limit orders, then open
  limit orders — each a separate rounded step. Merging them into one reserve doesn't match
  the on-chain rounding, so they have to be walked separately.

Correctness here means matching the on-chain program, not a re-derivation of the math. Every
value is checked against `swapQuote` on the same state; the harness is in `validation/`.
