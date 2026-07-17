# Changelog

## 0.4.0

Token-2022 support — transfer fees priced exactly, transfer-altering extensions refused
rather than mis-quoted. Swap math for standard pools is unchanged; the reference self-test
still matches the on-chain program to the lamport.

- **Transfer fees applied.** New `parse_mint(mint_bytes, owner)` decodes a mint's Token-2022
  extensions; `quote_with_mints(...)` (and `quote(..., fee_in=, fee_out=)`) apply the fee as
  an outer layer — on the input before the pool and the output after — matching on-chain
  `calculate_fee` including the per-transfer `maximum_fee` cap. `Quote` now reports
  `transfer_fee_in`, `transfer_fee_out`, and `gross_amount_out`.
- **Unquotable mints refused.** `parse_mint` raises `UnsupportedMint` for transfer hooks,
  non-transferable, confidential-transfer, pausable, and unrecognized extensions — so a pool
  like MU/USDC (transfer hook) declines instead of returning a wrong number.
- **New exports:** `quote_with_mints`, `parse_mint`, `MintInfo`, `TransferFee`,
  `UnsupportedMint`.
- **New regression:** `validation/check_token2022.py` covers fee math, the cap, and every
  refusal case.

## 0.3.0

Packaging release — no changes to swap math or the public API; every quote still matches the
on-chain program to the lamport.

- Published on PyPI: `pip install meteora-dlmm`.
- `python -m meteora_dlmm.selftest` reproduces the four reference quotes (diff = 0) from an
  installed copy; the reference fixture is bundled so it works with no repo checkout.
- Version is single-sourced from package metadata (no more hardcoded `__version__`).
- Ships `py.typed` (PEP 561) so type checkers see the annotations.
- Optional `[rpc]` extra for the RPC example; the library itself stays dependency-free.

## 0.2.0

A correctness release. **Breaking**: two decoder signatures changed, and `quote()` now raises
where it used to silently return a wrong number.

### Fixed

- **`quote()` couldn't tell "the pool is drained" from "you didn't fetch enough BinArrays".**
  It walked past the last loaded array, treated the bins it couldn't see as empty, and returned
  a smaller number with no signal — on an 8-array window a 1000-SOL swap came back ~20% low and
  looked like a normal answer. `PoolState` now tracks which arrays it holds, and `quote()` raises
  `InsufficientBinArrays` (carrying the missing `bin_id`, the unfilled input, and the partial
  `Quote`) rather than guessing. Pass `strict=False` to get the partial back instead, with
  `complete=False` marking `amount_out` as a lower bound. If you fetched *every* array the pool
  has, pass `exhaustive=True` and a short fill is correctly reported as a drained pool.

- **The decoder could silently drop bins.** `bin_id` was derived from the float log of the stored
  price behind a `raw < 1e9` guard, and anything above that bound was skipped rather than raising.
  It now comes from the BinArray header index (`bin_id = index * 70 + slot`), the way the program
  itself addresses bins — no floats, no filter. Verified identical to the old derivation on every
  bin of the reference pool, so no result changes. In practice the old bound was hard to reach
  (`raw` scales as `10**(quote_decimals - base_decimals)`, so ordinary 6/9 and 9/6 pairs sit near
  0.001–1; four live pools were screened and all came in 10+ orders of magnitude under it). This
  is a latent-robustness fix, not a live-breakage fix — but a decoder that quietly discards data
  it can't parse shouldn't stay that way, and DLMM is permissionless.

- **Duplicate BinArrays were summed**, double-counting that liquidity. Now raises `DecodeError`.

### Added

- `exhaustive=True` on `PoolState.from_accounts()`, plus `is_loaded()`, `loaded_bin_range()`,
  `loaded_arrays`, and `array_index_of()`.
- `Quote.complete` / `.remaining_in` / `.missing_bin_id`. Read the first two together:
  `complete` + `remaining_in == 0` is a full fill; `complete` + `remaining_in > 0` is a drained
  pool, and `amount_out` is still exact; `not complete` means the walk ran out of *data* and
  `amount_out` is only a lower bound.
- `DecodeError` on short accounts, BinArrays from more than one pool, and a bin with zero price
  but non-zero liquidity. Optional `lb_pair_key` to assert the arrays belong to the pool you think.
- `token_x_mint` / `token_y_mint` on `PoolState`, so decimals resolve from a pool address alone.

### Changed

- `decode_lb_pair()` returns 6 values (adds the two mints).
- `decode_bin_arrays()` drops its `bin_step` argument and returns `(bins, loaded_array_indices)`.
- The bin walk terminates at the program's real bounds (±443,636), not an arbitrary iteration guard.
- `check_quote.py` now reports whether each comparison was a full fill or a partial one bounded by
  the captured bin window, instead of counting both as wins.

### Migration

- Unpack six values from `decode_lb_pair()`.
- `bins, loaded = decode_bin_arrays(arrays)` — no `bin_step`.
- Anything relying on the old silent partial-fill must catch `InsufficientBinArrays`, or pass
  `strict=False` and check `Quote.complete`.
- `PoolState.from_accounts()` and `quote(pool, amount_in, swap_for_y)` are otherwise unchanged.

### Validation

Neither fix touches the swap math. `check_quote.py` still reports `max |diff| = 0` against the
SDK's `swapQuote`, and `live_check.py` still scores real executed swaps at 0.0001% median error.
What the committed fixtures do and don't demonstrate is spelled out in `LIMITATIONS.md`.

## 0.1.0

Initial release. Meteora DLMM decode + exact-in quote (bin walk, depth caps, variable-fee ramp,
three-tier limit-order fill), matched to 0 lamports against the on-chain program's `swapQuote`,
with a reproducible diff harness.
