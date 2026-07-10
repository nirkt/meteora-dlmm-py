"""The DLMM fee: a flat base fee plus a variable fee that grows with volatility.

The variable fee ramps as a swap moves across bins — the volatility accumulator gets
bigger the farther the swap travels from its starting bin, so later bins can cost more.
`update_reference` handles the time decay at the start of a swap; `update_va` runs once
per bin as the swap crosses it.
"""
from dataclasses import dataclass
from .constants import (
    FEE_PRECISION, MAX_FEE_RATE, BASIS_POINT_MAX, VAR_FEE_DENOMINATOR,
)


@dataclass
class StaticParams:
    base_factor: int
    base_fee_power_factor: int
    variable_fee_control: int
    max_volatility_accumulator: int
    filter_period: int
    decay_period: int
    reduction_factor: int
    protocol_share: int = 0


@dataclass
class VariableParams:
    volatility_accumulator: int
    volatility_reference: int
    index_reference: int
    last_update_timestamp: int


def _ceil_div(a, b):
    return (a + b - 1) // b if b else 0


def base_fee(bin_step, sp):
    return sp.base_factor * bin_step * 10 * (10 ** sp.base_fee_power_factor)


def variable_fee(bin_step, sp, vp):
    if sp.variable_fee_control <= 0:
        return 0
    squared = (vp.volatility_accumulator * bin_step) ** 2
    return _ceil_div(sp.variable_fee_control * squared, VAR_FEE_DENOMINATOR)


def total_fee(bin_step, sp, vp):
    """Fee rate numerator over FEE_PRECISION, capped at MAX_FEE_RATE."""
    return min(base_fee(bin_step, sp) + variable_fee(bin_step, sp, vp), MAX_FEE_RATE)


def update_reference(active_id, vp, sp, timestamp):
    """Time-decay the volatility reference at swap start (mutates `vp`)."""
    elapsed = timestamp - vp.last_update_timestamp
    if elapsed >= sp.filter_period:
        vp.index_reference = active_id
        if elapsed < sp.decay_period:
            vp.volatility_reference = (vp.volatility_accumulator * sp.reduction_factor) // BASIS_POINT_MAX
        else:
            vp.volatility_reference = 0


def update_va(active_id, vp, sp):
    """Recompute the volatility accumulator for the current bin (mutates `vp`)."""
    delta = abs(vp.index_reference - active_id)
    vp.volatility_accumulator = min(
        vp.volatility_reference + delta * BASIS_POINT_MAX,
        sp.max_volatility_accumulator,
    )


# fee applied on input, matching getExcludedFeeAmount / getIncludedFeeAmount
def excluded_in(amount, fee_rate):
    return amount - _ceil_div(amount * fee_rate, FEE_PRECISION)


def included_in(excluded, fee_rate):
    return _ceil_div(excluded * FEE_PRECISION, FEE_PRECISION - fee_rate)
