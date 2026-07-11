"""Decode LbPair and BinArray accounts from raw bytes into a PoolState, with no SDK dependency.
Bin ids come from the BinArray header index; PoolState records which arrays were loaded, and
whether that set is every array the pool has (exhaustive) or just a window around the active bin."""
import struct
from dataclasses import dataclass, field

from .constants import (
    Q64, BIN_ARRAY_HEADER, BIN_STRIDE, BINS_PER_ARRAY,
    OFF_BA_INDEX, OFF_BA_LB_PAIR,
    OFF_AMOUNT_X, OFF_AMOUNT_Y, OFF_PRICE, OFF_OPEN_ORDER, OFF_PROCESSED_ORDER, OFF_ASK_SIDE,
    OFF_BASE_FACTOR, OFF_FILTER_PERIOD, OFF_DECAY_PERIOD, OFF_REDUCTION_FACTOR,
    OFF_VARIABLE_FEE_CONTROL, OFF_MAX_VOLATILITY_ACC, OFF_PROTOCOL_SHARE, OFF_BASE_FEE_POWER,
    OFF_VOLATILITY_ACC, OFF_VOLATILITY_REF, OFF_INDEX_REF, OFF_LAST_UPDATE_TS,
    OFF_ACTIVE_ID, OFF_BIN_STEP, OFF_TOKEN_X_MINT, OFF_TOKEN_Y_MINT,
)
from .fees import StaticParams, VariableParams


class DecodeError(ValueError):
    pass


@dataclass
class Bin:
    bin_id: int
    amount_x: int
    amount_y: int
    price_x64: int
    open_order: int = 0
    processed_order: int = 0
    ask_side: int = 0


def array_index_of(bin_id):
    return bin_id // BINS_PER_ARRAY


@dataclass
class PoolState:
    active_id: int
    bin_step: int
    decimals_x: int
    decimals_y: int
    static_params: StaticParams
    variable_params: VariableParams
    bins: dict = field(default_factory=dict)
    loaded_arrays: set = field(default_factory=set)
    exhaustive: bool = False
    token_x_mint: bytes = b""
    token_y_mint: bytes = b""

    def is_loaded(self, bin_id):
        return array_index_of(bin_id) in self.loaded_arrays

    def loaded_bin_range(self):
        if not self.loaded_arrays:
            return (0, -1)
        lo, hi = min(self.loaded_arrays), max(self.loaded_arrays)
        return (lo * BINS_PER_ARRAY, hi * BINS_PER_ARRAY + BINS_PER_ARRAY - 1)

    def spot_price(self):
        b = self.bins.get(self.active_id)
        if not b or b.price_x64 == 0:
            return 0.0
        return (b.price_x64 / Q64) * (10 ** (self.decimals_x - self.decimals_y))

    @classmethod
    def from_accounts(cls, lb_pair, bin_arrays, decimals_x, decimals_y, lb_pair_key=None,
                      exhaustive=False):
        sp, vp, active_id, bin_step, mint_x, mint_y = decode_lb_pair(lb_pair)
        _verify_arrays_belong(bin_arrays, lb_pair_key)
        bins, loaded = decode_bin_arrays(bin_arrays)
        return cls(active_id, bin_step, decimals_x, decimals_y, sp, vp, bins, loaded,
                   exhaustive, mint_x, mint_y)


def _verify_arrays_belong(bin_arrays, lb_pair_key=None):
    keys = {bytes(d[OFF_BA_LB_PAIR:OFF_BA_LB_PAIR + 32]) for d in bin_arrays
            if len(d) >= BIN_ARRAY_HEADER}
    if len(keys) > 1:
        raise DecodeError("BinArrays reference more than one LbPair — mixed pools")
    if lb_pair_key is not None and keys and bytes(lb_pair_key) not in keys:
        raise DecodeError("BinArrays do not belong to this LbPair")


def decode_lb_pair(data):
    if len(data) < OFF_TOKEN_Y_MINT + 32:
        raise DecodeError(f"LbPair account too short: {len(data)} bytes")
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
    mint_x = bytes(data[OFF_TOKEN_X_MINT:OFF_TOKEN_X_MINT + 32])
    mint_y = bytes(data[OFF_TOKEN_Y_MINT:OFF_TOKEN_Y_MINT + 32])
    return sp, vp, i32(OFF_ACTIVE_ID), u16(OFF_BIN_STEP), mint_x, mint_y


def decode_bin_arrays(bin_arrays):
    bins = {}
    loaded = set()
    for data in bin_arrays:
        if len(data) < BIN_ARRAY_HEADER + BIN_STRIDE:
            raise DecodeError(f"BinArray account too short: {len(data)} bytes")
        arr_idx = struct.unpack_from("<q", data, OFF_BA_INDEX)[0]
        if arr_idx in loaded:
            raise DecodeError(f"BinArray index {arr_idx} passed twice")
        loaded.add(arr_idx)

        n_slots = min((len(data) - BIN_ARRAY_HEADER) // BIN_STRIDE, BINS_PER_ARRAY)
        for slot in range(n_slots):
            off = BIN_ARRAY_HEADER + slot * BIN_STRIDE
            price = int.from_bytes(data[off + OFF_PRICE:off + OFF_PRICE + 16], "little")
            ax = int.from_bytes(data[off + OFF_AMOUNT_X:off + OFF_AMOUNT_X + 8], "little")
            ay = int.from_bytes(data[off + OFF_AMOUNT_Y:off + OFF_AMOUNT_Y + 8], "little")
            oo = int.from_bytes(data[off + OFF_OPEN_ORDER:off + OFF_OPEN_ORDER + 8], "little")
            po = int.from_bytes(data[off + OFF_PROCESSED_ORDER:off + OFF_PROCESSED_ORDER + 8], "little")
            ask = data[off + OFF_ASK_SIDE]

            if price == 0:
                if ax or ay or oo or po:
                    raise DecodeError(
                        f"bin {arr_idx * BINS_PER_ARRAY + slot} has zero price but non-zero "
                        f"liquidity (x={ax} y={ay} open={oo} processed={po}) — layout mismatch"
                    )
                continue

            bin_id = arr_idx * BINS_PER_ARRAY + slot
            bins[bin_id] = Bin(bin_id, ax, ay, price, oo, po, ask)
    return bins, loaded
