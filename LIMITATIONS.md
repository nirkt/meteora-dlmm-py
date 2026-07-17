# Limitations & scope

What the library does, what it doesn't, and the bugs I hit getting the numbers to match the
on-chain program exactly.

## What it covers

- **Meteora DLMM only.** No CPMM (Raydium/Orca) or Whirlpool CLMM here.
- **Exact-in swaps.** You give an input amount, it gives the output. No exact-out.
- **The current DLMM program** (with limit orders, from the Dec 2025 upgrade). The decoder
  reads that bin layout, checked against a live pool. For older or forked pools that use the
  classic bin layout, pass `support_limit_order=False` to `quote()` — otherwise it would
  read the limit-order offsets (+112/+128/+140) as unrelated bytes.

## Assumptions

- **Token-2022 transfer fees: supported.** Decode each mint with `parse_mint(mint_bytes,
  owner)` and pass the result to `quote_with_mints(...)` (or pass `TransferFee` objects to
  `quote(..., fee_in=, fee_out=)` directly). The fee is applied as an outer layer — skimmed
  from the input before it reaches the pool and from the output after it leaves — matching the
  on-chain `calculate_fee` (ceil, capped at `maximum_fee`). Standard SPL pools are unaffected;
  omit the mint info and behavior is exactly as before.
- **Token-2022 transfer hooks and other transfer-altering extensions: refused, not guessed.**
  A transfer hook is an arbitrary program run on every transfer; its effect can't be computed
  off-chain without simulation, which would defeat a local quoter. `parse_mint` raises
  `UnsupportedMint` (carrying the offending extension id) for transfer hooks, non-transferable
  mints, confidential-transfer mints, pausable mints, and any unrecognized extension that
  might alter transfers. Refusing is deliberate: a wrong quote on such a token could cost an
  integrator real money, so the library declines rather than returns a confident wrong number.
- **You provide the liquidity, and the library will tell you when you haven't provided
  enough.** `quote()` only walks the BinArrays you pass in. If a swap would walk past the last
  one you fetched, it raises `InsufficientBinArrays` rather than treating the unknown bins as
  empty and quietly returning a smaller number. The exception carries the missing `bin_id`, the
  unfilled input, and the partial `Quote`, so you can fetch that array and re-quote. Pass
  `strict=False` if you want the partial back instead — `Quote.complete` will be `False` and
  `amount_out` is then a lower bound, not an answer.

  If you fetched *every* BinArray the pool has (`getProgramAccounts` does; arrays only exist where
  liquidity was placed), pass `exhaustive=True`. There is then no window to run off the end of, so
  a swap that runs short means the pool is drained rather than under-fetched, and `quote()` returns
  `complete=True` with `remaining_in > 0` — an exact partial fill. The library cannot infer this
  for itself: it knows which arrays it holds, not whether that is all of them. Only the caller
  knows how the fetch was done.
- **Fee-decay timestamp.** The variable fee's decay depends on the current time. `quote()`
  uses "now" by default. To reproduce one specific past swap, pass that swap's block time —
  a sub-second gap from the program's clock can flip the decay branch right at the
  `filterPeriod` boundary. That's a rare one-off edge, not a systematic error.

## How far it's been validated

Be precise about this, because the precision claim is the whole point of the project.

**Verifiable from this repo, with no RPC key** (both fixtures are the same 1bp SOL/USDC pool):

- `check_quote.py` — 0 lamports against the program's `swapQuote`, X→Y, on full fills crossing
  1 to 20 bins, with a nonzero volatility accumulator so the fee ramp is genuinely in play.
- `live_check.py` — 10 real executed swaps, both directions, median relative error 0.0001%,
  max 0.001%. The residual is pre-snapshot staleness, not the math.

**Not verifiable from this repo:**

- **Other bin steps and other pairs.** The math doesn't depend on bin step, so they should
  pass — but "should" isn't "did". Widening this is M1.
- **Y→X against `swapQuote`.** The real-swap fixture covers both directions; the `swapQuote`
  fixture is X→Y only.
- **Limit orders.** The committed pool carries limit orders in only 2 of its 3264 liquid bins,
  and the only reference swap that reaches them is the one that partial-fills. The
  `processed_order` tier is never exercised by the committed fixture at all. The three-tier
  fill was developed against, and matched on, a 4bp limit-order pool with orders in roughly a
  quarter of its bins — but that capture isn't committed here, so take it as a claim, not as
  evidence, until the multi-pool sweep lands.

**A note on partial fills.** The largest reference swap drains every captured BinArray and
stops at the window edge with 23% of its input unfilled. The SDK, called with partial-fill
enabled over the same window, stops in the same place — so `diff = 0` there is a genuine
apples-to-apples match. It is *not* evidence that a swap that size prices correctly on-chain,
where more BinArrays exist. `check_quote.py` labels these rows rather than counting them.

## Bugs I hit on the way

Getting to `diff = 0` meant fixing a few subtle bugs. Each one is a real DLMM gotcha worth
knowing about.

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
- **Never derive `bin_id` from the price.** (Fixed in 0.2.0.) The decoder used to recover each
  bin's id by taking the float log of its stored Q64.64 price, guarded by `raw < 1e9` to keep
  the float sane — and that guard silently *dropped* every bin above it, rather than failing.
  The id is right there in the BinArray header (`bin_id = index * 70 + slot`), so the whole
  float detour was unnecessary. Verified identical to the old derivation on every bin of the
  reference pool, so this changed no result; it removed a landmine.

  How reachable was the landmine? Less than it first looks. `raw = ui_price * 10**(dec_y - dec_x)`
  — note that's *quote* minus *base* — so tripping `raw >= 1e9` needs a **low**-decimal base
  against a **high**-decimal quote at a meaningful price: a 0-decimal token worth ≥1 SOL, or a
  2-decimal token worth ≥100 SOL. For the ordinary 6/9 and 9/6 decimal pairs that make up
  almost every pool on Meteora, `raw` sits around 0.001–1 and the bound is structurally out of
  reach. Four live pools were screened (6-dec and 11-dec bases against WSOL and USDC) and all
  came in 10+ orders of magnitude below it. But DLMM is permissionless — anyone can create a
  pool with a 0-decimal token tomorrow — and a decoder that silently discards data it doesn't
  like is not something to leave in place because today's pools happen to avoid it.
- **Never let a swap walk off the end of the bins you loaded.** (Fixed in 0.2.0.) The walk used
  to step through un-fetched bins as if they were empty, returning an under-count with no
  signal. On an 8-array window a 1000-SOL swap came back ~20% low and looked like a normal
  answer. "Ran out of liquidity" and "ran out of *data*" are not the same event and must not
  produce the same number.
- **Duplicate BinArrays used to be summed.** Passing the same account twice merged its bins
  into the existing ones and doubled that liquidity. It now raises.

Correctness here means matching the on-chain program, not a re-derivation of the math. Every
value is checked against `swapQuote` on the same state; the harness is in `validation/`.
