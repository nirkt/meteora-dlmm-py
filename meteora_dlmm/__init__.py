"""meteora_dlmm — a lamport-exact Meteora DLMM swap-quote library.

Validated bin-for-bin against the on-chain program (via the SDK's swapQuote),
including the dynamic variable-fee ramp and on-chain limit orders.

    from meteora_dlmm import PoolState, quote

    pool = PoolState.from_accounts(lb_pair_bytes, bin_array_bytes, dec_x=9, dec_y=6)
    result = quote(pool, amount_in=1_000_000_000, swap_for_y=True)
    print(result.amount_out, result.bins_crossed)
"""
from .constants import Q64, BIN_ARRAY_SIZE
from .decode import Bin, PoolState, decode_lb_pair, decode_bin_arrays
from .fees import StaticParams, VariableParams, total_fee
from .quote import Quote, quote

__all__ = [
    "PoolState", "quote", "Quote", "Bin",
    "decode_lb_pair", "decode_bin_arrays",
    "StaticParams", "VariableParams", "total_fee", "Q64", "BIN_ARRAY_SIZE",
]
__version__ = "0.1.0"
