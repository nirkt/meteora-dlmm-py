"""Price an exact-in swap by walking the bins the way the on-chain program does.

It fills bin by bin — capped by each bin's real liquidity — applies the fee (which ramps
across bins), and fills each bin's AMM reserve then its limit orders. Matches the program's
swap output to the lamport.
"""
import copy
import time
from dataclasses import dataclass

from .constants import Q64
from .fees import total_fee, update_reference, update_va, excluded_in, included_in, _ceil_div


@dataclass
class Quote:
    amount_out: int
    bins_crossed: int


def _amount_out(price, amount, swap_for_y):        # getAmountOut, floor
    return (amount * price) // Q64 if swap_for_y else (amount * Q64) // price


def _amount_in_up(price, out, swap_for_y):         # getAmountIn, ceil
    return _ceil_div(out * Q64, price) if swap_for_y else _ceil_div(out * price, Q64)


def _fill(price, amount, reserve, swap_for_y):
    """One liquidity tier -> (input_used, input_left, output). Matches calculateExactInFillAmount."""
    if reserve <= 0:
        return 0, amount, 0
    max_in = _amount_in_up(price, reserve, swap_for_y)
    if amount >= max_in:
        return max_in, amount - max_in, reserve                      # tier depleted
    return amount, 0, _amount_out(price, amount, swap_for_y)         # tier absorbs the rest


def quote(pool, amount_in, swap_for_y, timestamp=None, support_limit_order=True):
    """Quote an exact-in swap against a `PoolState`.

    swap_for_y=True spends token X (walks down / falling price); False spends token Y.
    `timestamp` (unix seconds) drives the fee-decay reference; defaults to now.
    """
    if timestamp is None:
        timestamp = time.time()
    sp = pool.static_params
    vp = copy.copy(pool.variable_params)
    update_reference(pool.active_id, vp, sp, timestamp)

    step = -1 if swap_for_y else 1
    current, remaining, out_total, crossed, guard = pool.active_id, amount_in, 0, 0, 40000

    while remaining > 0 and guard:
        guard -= 1
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

        # three tiers at the same price and fee: AMM -> processed orders -> open orders
        used, out, left = 0, 0, excl
        for reserve in (mm_reserve, proc_amt, open_amt):
            if left <= 0:
                break
            tier_in, left, tier_out = _fill(b.price_x64, left, reserve, swap_for_y)
            used += tier_in
            out += tier_out
        out_total += out

        if left != 0:                                   # bin fully consumed -> cross
            remaining -= included_in(used, fee_rate)
            crossed += 1
            current += step
        else:                                           # bin absorbed the remainder
            break

    return Quote(amount_out=out_total, bins_crossed=crossed + 1)
