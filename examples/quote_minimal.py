"""Minimal integration snippet — drop this shape into your own code.

You supply the raw account bytes (from whatever RPC client you already use);
the library decodes and quotes. No SDK, no network calls inside the library.
"""
from meteora_dlmm import PoolState, quote

# lb_pair_bytes:      the LbPair account's data (bytes)
# bin_array_byte_list: list of BinArray account data (bytes), covering the swap range
def price_a_swap(lb_pair_bytes, bin_array_byte_list, amount_in, swap_for_y):
    pool = PoolState.from_accounts(
        lb_pair_bytes,
        bin_array_byte_list,
        decimals_x=9,   # e.g. SOL
        decimals_y=6,   # e.g. USDC
    )
    # quote() raises InsufficientBinArrays if the swap walks past the BinArrays you passed in,
    # rather than treating the bins it can't see as empty and returning a number that's too low.
    # Catch it, fetch the array it names, and re-quote — or pass strict=False to get the partial
    # back with result.complete == False.
    result = quote(pool, amount_in, swap_for_y=swap_for_y)
    return result.amount_out, result.bins_crossed


if __name__ == "__main__":
    print("Supply real account bytes to price_a_swap(); see quote_from_rpc.py for a full RPC example.")
