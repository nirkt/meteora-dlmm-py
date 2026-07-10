"""Decode Meteora DLMM accounts from raw bytes — no SDK dependency.

`PoolState.from_accounts(lb_pair_bytes, bin_array_bytes, decimals_x, decimals_y)`
gives everything `quote()` needs, straight from `getAccountInfo` / `getMultipleAccounts`.
"""
import math
import struct
from dataclasses import dataclass, field

from .constants import (
    Q64, BIN_ARRAY_HEADER, BIN_STRIDE,
    OFF_AMOUNT_X, OFF_AMOUNT_Y, OFF_PRICE, OFF_OPEN_ORDER, OFF_PROCESSED_ORDER, OFF_ASK_SIDE,
    OFF_BASE_FACTOR, OFF_FILTER_PERIOD, OFF_DECAY_PERIOD, OFF_REDUCTION_FACTOR,
    OFF_VARIABLE_FEE_CONTROL, OFF_MAX_VOLATILITY_ACC, OFF_PROTOCOL_SHARE, OFF_BASE_FEE_POWER,
    OFF_VOLATILITY_ACC, OFF_VOLATILITY_REF, OFF_INDEX_REF, OFF_LAST_UPDATE_TS,
    OFF_ACTIVE_ID, OFF_BIN_STEP,
)
from .fees import StaticParams, VariableParams


@dataclass
class Bin:
    bin_id: int
    amount_x: int          # base-unit reserves (already net of protocol fees)
    amount_y: int
    price_x64: int         # raw Q64.64 price
    open_order: int = 0    # limit-order liquidity
    processed_order: int = 0
    ask_side: int = 0


@dataclass
class PoolState:
    active_id: int
    bin_step: int
    decimals_x: int
    decimals_y: int
    static_params: StaticParams
    variable_params: VariableParams
    bins: dict = field(default_factory=dict)   # bin_id -> Bin

    def spot_price(self):
        """Quote-per-base UI price at the active bin (e.g. USDC per SOL)."""
        b = self.bins.get(self.active_id)
        if not b or b.price_x64 == 0:
            return 0.0
        return (b.price_x64 / Q64) * (10 ** (self.decimals_x - self.decimals_y))

    @classmethod
    def from_accounts(cls, lb_pair, bin_arrays, decimals_x, decimals_y):
        sp, vp, active_id, bin_step = decode_lb_pair(lb_pair)
        bins = decode_bin_arrays(bin_arrays, bin_step)
        return cls(active_id, bin_step, decimals_x, decimals_y, sp, vp, bins)


def decode_lb_pair(data):
    """Decode an LbPair account -> (StaticParams, VariableParams, active_id, bin_step)."""
    u16 = lambda o: struct.unpack_from("<H", data, o)[0]
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    i32 = lambda o: struct.unpack_from("<i", data, o)[0]
    i64 = lambda o: struct.unpack_from("<q", data, o)[0]
    sp = StaticParams(
        base_factor=u16(OFF_BASE_FACTOR),
        base_fee_power_factor=data[OFF_BASE_FEE_POWER],
        variable_fee_control=u32(OFF_VARIABLE_FEE_CONTROL),
        max_volatility_accumulator=u32(OFF_MAX_VOLATILITY_ACC),
        filter_period=u16(OFF_FILTER_PERIOD),
        decay_period=u16(OFF_DECAY_PERIOD),
        reduction_factor=u16(OFF_REDUCTION_FACTOR),
        protocol_share=u16(OFF_PROTOCOL_SHARE),
    )
    vp = VariableParams(
        volatility_accumulator=u32(OFF_VOLATILITY_ACC),
        volatility_reference=u32(OFF_VOLATILITY_REF),
        index_reference=i32(OFF_INDEX_REF),
        last_update_timestamp=i64(OFF_LAST_UPDATE_TS),
    )
    return sp, vp, i32(OFF_ACTIVE_ID), u16(OFF_BIN_STEP)


def decode_bin_arrays(bin_arrays, bin_step):
    """Decode a list of BinArray account byte strings -> {bin_id: Bin}."""
    bins = {}
    ln = math.log(1 + bin_step / 10000)
    for data in bin_arrays:
        if len(data) < BIN_ARRAY_HEADER + BIN_STRIDE:
            continue
        for i in range((len(data) - BIN_ARRAY_HEADER) // BIN_STRIDE):
            off = BIN_ARRAY_HEADER + i * BIN_STRIDE
            if off + BIN_STRIDE > len(data):
                break
            price = int.from_bytes(data[off + OFF_PRICE:off + OFF_PRICE + 16], "little")
            if price == 0 or price >= 2 ** 127:
                continue
            raw = price / Q64
            if raw <= 0 or raw >= 1e9:
                continue
            bin_id = int(round(math.log(raw) / ln))
            ax = int.from_bytes(data[off + OFF_AMOUNT_X:off + OFF_AMOUNT_X + 8], "little")
            ay = int.from_bytes(data[off + OFF_AMOUNT_Y:off + OFF_AMOUNT_Y + 8], "little")
            oo = int.from_bytes(data[off + OFF_OPEN_ORDER:off + OFF_OPEN_ORDER + 8], "little")
            po = int.from_bytes(data[off + OFF_PROCESSED_ORDER:off + OFF_PROCESSED_ORDER + 8], "little")
            ask = data[off + OFF_ASK_SIDE]
            if bin_id in bins:
                e = bins[bin_id]
                bins[bin_id] = Bin(bin_id, e.amount_x + ax, e.amount_y + ay, price,
                                   e.open_order + oo, e.processed_order + po, ask)
            else:
                bins[bin_id] = Bin(bin_id, ax, ay, price, oo, po, ask)
    return bins
