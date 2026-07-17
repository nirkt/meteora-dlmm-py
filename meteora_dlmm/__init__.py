"""meteora-dlmm-py: a pure-Python Meteora DLMM swap quoter, lamport-exact against the program."""
from .decode import PoolState, Bin, DecodeError, array_index_of
from .quote import quote, quote_with_mints, Quote, InsufficientBinArrays
from .fees import StaticParams, VariableParams, total_fee
from .token2022 import parse_mint, MintInfo, TransferFee, UnsupportedMint

__all__ = [
    "PoolState", "Bin", "DecodeError", "array_index_of",
    "quote", "quote_with_mints", "Quote", "InsufficientBinArrays",
    "StaticParams", "VariableParams", "total_fee",
    # Token-2022 support
    "parse_mint", "MintInfo", "TransferFee", "UnsupportedMint",
]

try:
    from importlib.metadata import version as _v
    __version__ = _v("meteora-dlmm")
except Exception:
    __version__ = "0.0.0+local"
