"""On-chain layout and fee constants for the Meteora DLMM program.

All values verified against the MeteoraAg/dlmm program source.
"""

Q64 = 2 ** 64  # Q64.64 fixed-point scale (SCALE_OFFSET = 64)

# --- BinArray account layout ---
BIN_ARRAY_HEADER = 56          # discriminator(8) + index(8) + version(1) + pad(7) + lbPair(32)
BIN_STRIDE = 144               # bytes per Bin
BINS_PER_ARRAY = 70
BIN_ARRAY_SIZE = BIN_ARRAY_HEADER + BINS_PER_ARRAY * BIN_STRIDE  # 10136

# --- Bin field offsets, relative to the start of each 144-byte bin ---
OFF_AMOUNT_X = 0               # u64
OFF_AMOUNT_Y = 8               # u64
OFF_PRICE = 16                 # u128, Q64.64 RAW price = (1 + bin_step/1e4)^id * 2^64 (NOT a sqrt price)
OFF_OPEN_ORDER = 112           # u64, limit-order open amount
OFF_PROCESSED_ORDER = 128      # u64, limit-order processed-remaining amount
OFF_ASK_SIDE = 140             # u8,  limit-order side flag

# --- LbPair account offsets (absolute, incl. 8-byte discriminator) ---
OFF_BASE_FACTOR = 8            # u16
OFF_FILTER_PERIOD = 10         # u16
OFF_DECAY_PERIOD = 12          # u16
OFF_REDUCTION_FACTOR = 14      # u16
OFF_VARIABLE_FEE_CONTROL = 16  # u32
OFF_MAX_VOLATILITY_ACC = 20    # u32
OFF_PROTOCOL_SHARE = 32        # u16
OFF_BASE_FEE_POWER = 34        # u8
OFF_VOLATILITY_ACC = 40        # u32
OFF_VOLATILITY_REF = 44        # u32
OFF_INDEX_REF = 48             # i32
OFF_LAST_UPDATE_TS = 56        # i64
OFF_ACTIVE_ID = 76             # i32
OFF_BIN_STEP = 80              # u16

# --- Fee math (numerators over FEE_PRECISION) ---
FEE_PRECISION = 1_000_000_000
MAX_FEE_RATE = 100_000_000     # 10% cap
BASIS_POINT_MAX = 10_000
VAR_FEE_DENOMINATOR = 100_000_000_000
