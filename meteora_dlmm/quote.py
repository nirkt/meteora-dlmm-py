"""Price an exact-in swap by walking bins the way the on-chain program does.
Raises InsufficientBinArrays if the walk leaves the loaded bin window rather than guessing;
on an exhaustive PoolState there is no window to leave, so a short fill means the pool is drained."""
import copy
import time
from dataclasses import dataclass

from .constants import Q64, MIN_BIN_ID, MAX_BIN_ID
from .decode import array_index_of
from .fees import total_fee, update_reference, update_va, excluded_in, included_in, _ceil_div
from .token2022 import TransferFee


class InsufficientBinArrays(Exception):
    def __init__(self, bin_id, remaining_in, partial):
        self.bin_id = bin_id
        self.remaining_in = remaining_in
        self.partial = partial
        super().__init__(
            f"swap needs bin {bin_id} (BinArray index {array_index_of(bin_id)}) which was not "
            f"loaded; {remaining_in} input units unfilled. Fetch that array and re-quote."
        )


@dataclass
class Quote:
    amount_out: int          # what the user actually RECEIVES (net of output transfer fee)
    bins_crossed: int
    complete: bool = True
    remaining_in: int = 0
    missing_bin_id: int = None
    transfer_fee_in: int = 0    # skimmed by the input mint's transfer fee, before the pool
    transfer_fee_out: int = 0   # skimmed by the output mint's transfer fee, after the pool
    gross_amount_out: int = 0   # pool output before the output transfer fee


def _amount_out(price, amount, swap_for_y):
    return (amount * price) // Q64 if swap_for_y else (amount * Q64) // price


def _amount_in_up(price, out, swap_for_y):
    return _ceil_div(out * Q64, price) if swap_for_y else _ceil_div(out * price, Q64)


def _fill(price, amount, reserve, swap_for_y):
    if reserve <= 0:
        return 0, amount, 0
    max_in = _amount_in_up(price, reserve, swap_for_y)
    if amount >= max_in:
        return max_in, amount - max_in, reserve
    return amount, 0, _amount_out(price, amount, swap_for_y)


def quote(pool, amount_in, swap_for_y, timestamp=None, support_limit_order=True, strict=True,
          fee_in: TransferFee = None, fee_out: TransferFee = None):
    """Price an exact-in swap.

    fee_in / fee_out apply the input/output token's Token-2022 transfer fee as an OUTER layer:
    the pool only ever sees post-input-fee tokens, and the user receives post-output-fee
    tokens. Pass them (from token2022.parse_mint) for transfer-fee pools; leave None for
    standard SPL pools, where behavior is unchanged.
    """
    if timestamp is None:
        timestamp = time.time()

    # Input transfer fee: the pool receives amount_in minus what the mint skims on transfer-in.
    transfer_fee_in = fee_in.fee_on(amount_in) if fee_in else 0
    pool_amount_in = amount_in - transfer_fee_in

    loaded_lo, loaded_hi = pool.loaded_bin_range()
    sp = pool.static_params
    vp = copy.copy(pool.variable_params)
    update_reference(pool.active_id, vp, sp, timestamp)

    step = -1 if swap_for_y else 1
    current, remaining, out_total, crossed = pool.active_id, pool_amount_in, 0, 0

    while remaining > 0:
        if current < MIN_BIN_ID or current > MAX_BIN_ID:
            break

        if not pool.is_loaded(current):
            if pool.exhaustive:
                if current < loaded_lo or current > loaded_hi:
                    break
                current += step
                continue
            partial = Quote(out_total, crossed, complete=False,
                            remaining_in=remaining, missing_bin_id=current)
            if strict:
                raise InsufficientBinArrays(current, remaining, partial)
            return partial

        b = pool.bins.get(current)
        if not b:
            current += step
            continue

        mm_reserve = b.amount_y if swap_for_y else b.amount_x
        open_amt = proc_amt = 0
        if support_limit_order:
            relevant = (swap_for_y and not b.ask_side) or ((not swap_for_y) and b.ask_side)
            if relevant:
                open_amt, proc_amt = b.open_order, b.processed_order
        if mm_reserve == 0 and open_amt == 0 and proc_amt == 0:
            current += step
            continue

        update_va(current, vp, sp)
        fee_rate = total_fee(pool.bin_step, sp, vp)
        excl = excluded_in(remaining, fee_rate)

        used, out, left = 0, 0, excl
        for reserve in (mm_reserve, proc_amt, open_amt):
            if left <= 0:
                break
            tier_in, left, tier_out = _fill(b.price_x64, left, reserve, swap_for_y)
            used += tier_in
            out += tier_out
        out_total += out

        if left != 0:
            remaining -= included_in(used, fee_rate)
            crossed += 1
            current += step
        else:
            fee_o = fee_out.fee_on(out_total) if fee_out else 0
            return Quote(amount_out=out_total - fee_o, bins_crossed=crossed + 1,
                         transfer_fee_in=transfer_fee_in, transfer_fee_out=fee_o,
                         gross_amount_out=out_total)

    fee_o = fee_out.fee_on(out_total) if fee_out else 0
    return Quote(amount_out=out_total - fee_o, bins_crossed=crossed + 1,
                 complete=True, remaining_in=remaining,
                 transfer_fee_in=transfer_fee_in, transfer_fee_out=fee_o,
                 gross_amount_out=out_total)


def quote_with_mints(pool, amount_in, swap_for_y, mint_x_info, mint_y_info,
                     timestamp=None, support_limit_order=True, strict=True):
    """Quote a swap given decoded mint info for both tokens.

    Resolves which mint is input vs output from swap_for_y (X->Y spends X, receives Y), pulls
    each side's transfer fee, and calls quote() with them. Raises UnsupportedMint upstream if
    either mint carries an extension we can't model — so a transfer-hook pool refuses here
    rather than returning a wrong number.

    mint_x_info / mint_y_info come from token2022.parse_mint(mint_bytes, owner).
    """
    if swap_for_y:
        fee_in = mint_x_info.transfer_fee
        fee_out = mint_y_info.transfer_fee
    else:
        fee_in = mint_y_info.transfer_fee
        fee_out = mint_x_info.transfer_fee
    return quote(pool, amount_in, swap_for_y, timestamp=timestamp,
                 support_limit_order=support_limit_order, strict=strict,
                 fee_in=fee_in, fee_out=fee_out)
