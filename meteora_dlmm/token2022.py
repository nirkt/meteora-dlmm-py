"""Token-2022 extension handling.

Two things stand between "quotes standard pools" and "quotes any pool, or honestly refuses":

  - **Transfer fees** have a clean off-chain formula. A `TransferFeeConfig` mint skims a
    basis-point fee (capped per transfer) on every transfer. The DLMM program moves tokens in
    and out, so the fee applies OUTSIDE the bin walk: on the input before it reaches the pool,
    and on the output after it leaves. We model that here and apply it as a wrapper in quote().

  - **Transfer hooks** are arbitrary programs run on every transfer. There is no off-chain
    formula — you would have to simulate them on-chain, which defeats a local quoter. So we
    DETECT a hook (or any other transfer-altering extension we can't model) and let quote()
    REFUSE with a typed error, rather than return a confident wrong number.

Mint bytes are read straight from getAccountInfo(mint). The classic SPL Token program has no
extensions; only Token-2022 mints carry the TLV region parsed below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Program owners. The account's owner tells us which token program governs the mint.
TOKEN_PROGRAM = bytes.fromhex(
    # TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
    "06ddf6e1d765a193d9cbe146ceeb79ac1cb485ed5f5b37913a8cf5857eff00a9"
)
TOKEN_2022_PROGRAM = bytes.fromhex(
    # TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb
    "06ddf6e1ee758fde18425dbce46ccddab61afc4d83b90d27febdf928d8a18bfc"
)

# Base SPL mint is 82 bytes. A Token-2022 mint with extensions is larger: 82-byte base, a byte
# 165 account-type discriminator (== 1 for Mint), then a TLV list from offset 166.
MINT_BASE_LEN = 82
ACCOUNT_TYPE_OFFSET = 165
TLV_START = 166
MINT_DECIMALS_OFFSET = 44

# Extension type ids (SPL Token-2022). We only need to know which ones alter transfers.
EXT_TRANSFER_FEE_CONFIG = 1
EXT_TRANSFER_HOOK = 14
# Extensions that change how much actually moves on a transfer, or forbid it. If any is
# present and we don't model it, quoting would diff — so we refuse.
EXT_NON_TRANSFERABLE = 9
EXT_CONFIDENTIAL_TRANSFER_MINT = 4
EXT_PAUSABLE = 44  # newer; pausing halts transfers entirely

# Extensions that are safe to ignore for pricing (metadata, pointers, delegates, account-state
# defaults). Presence of these alone does NOT force a refusal.
_HARMLESS = frozenset({
    2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
})


@dataclass
class TransferFee:
    """The currently-effective transfer fee for a mint (the 'newer' epoch config)."""
    basis_points: int
    max_fee: int  # absolute cap in base units, per transfer

    def fee_on(self, amount: int) -> int:
        # Matches the on-chain calculate_fee: ceil(amount * bps / 10_000), capped at max_fee.
        if self.basis_points == 0 or amount == 0:
            return 0
        raw = (amount * self.basis_points + 9_999) // 10_000
        return min(raw, self.max_fee)


class UnsupportedMint(Exception):
    """The mint uses a transfer-altering extension this library cannot model off-chain.

    Refusing is deliberate: a wrong quote on a transfer-hook token could cost an integrator
    real money. Carries the offending extension id so callers can branch on it.
    """
    def __init__(self, reason: str, extension: Optional[int] = None):
        self.reason = reason
        self.extension = extension
        super().__init__(reason)


@dataclass
class MintInfo:
    decimals: int
    is_token_2022: bool
    transfer_fee: Optional[TransferFee] = None
    # extension ids present, for diagnostics / caller inspection
    extensions: tuple = ()

    @property
    def quotable(self) -> bool:
        return True  # if we built one without raising, it's quotable (fee may still apply)


def _read_tlv(data: bytes):
    """Yield (ext_type, body_bytes) for each extension in a Token-2022 mint's TLV region."""
    if len(data) <= ACCOUNT_TYPE_OFFSET:
        return
    o = TLV_START
    n = len(data)
    while o + 4 <= n:
        ext_type = int.from_bytes(data[o:o + 2], "little")
        length = int.from_bytes(data[o + 2:o + 4], "little")
        body_start = o + 4
        if ext_type == 0 and length == 0:
            break
        body = data[body_start:body_start + length]
        yield ext_type, body
        o = body_start + length


def _parse_transfer_fee(body: bytes) -> Optional[TransferFee]:
    """Extract the *current* (newer) fee from a TransferFeeConfig extension body.

    Layout: transfer_fee_config_authority(32) withdraw_withheld_authority(32)
            withheld_amount(8)
            older: epoch(8) maximum_fee(8) transfer_fee_basis_points(2)
            newer: epoch(8) maximum_fee(8) transfer_fee_basis_points(2)
    The newer config is the last 18 bytes; it's the one in effect now (older is the previous
    epoch, kept for in-flight settlement). We price with newer.
    """
    if len(body) < 32 + 32 + 8 + 18 + 18:
        return None
    nb = len(body) - 18  # start of the newer TransferFee
    max_fee = int.from_bytes(body[nb + 8:nb + 16], "little")
    bps = int.from_bytes(body[nb + 16:nb + 18], "little")
    return TransferFee(basis_points=bps, max_fee=max_fee)


def parse_mint(data: bytes, owner: bytes) -> MintInfo:
    """Decode a mint account into a MintInfo, or raise UnsupportedMint if we can't model it.

    `owner` is the account's owner program (from getAccountInfo). Classic SPL -> no extensions,
    trivially quotable. Token-2022 -> walk the TLV and decide.
    """
    if len(data) < MINT_BASE_LEN:
        raise UnsupportedMint("mint account too short to be valid")
    decimals = data[MINT_DECIMALS_OFFSET]

    is_2022 = owner == TOKEN_2022_PROGRAM
    if not is_2022:
        return MintInfo(decimals=decimals, is_token_2022=False)

    fee: Optional[TransferFee] = None
    seen = []
    for ext_type, body in _read_tlv(data):
        seen.append(ext_type)
        if ext_type == EXT_TRANSFER_FEE_CONFIG:
            fee = _parse_transfer_fee(body)
        elif ext_type == EXT_TRANSFER_HOOK:
            # A hook *may* be a no-op (zero program id), but we can't know its effect without
            # running it. If a real hook program is set, refuse.
            hook_program = body[:32] if len(body) >= 32 else b""
            if hook_program and hook_program != bytes(32):
                raise UnsupportedMint(
                    "token uses a Token-2022 transfer hook, whose effect can't be computed "
                    "off-chain; refusing rather than returning a wrong quote",
                    extension=EXT_TRANSFER_HOOK,
                )
        elif ext_type == EXT_NON_TRANSFERABLE:
            raise UnsupportedMint("token is non-transferable", extension=EXT_NON_TRANSFERABLE)
        elif ext_type == EXT_CONFIDENTIAL_TRANSFER_MINT:
            # Confidential transfers can route amounts we can't observe; be conservative.
            raise UnsupportedMint(
                "token uses confidential transfers", extension=EXT_CONFIDENTIAL_TRANSFER_MINT)
        elif ext_type == EXT_PAUSABLE:
            raise UnsupportedMint("token is pausable", extension=EXT_PAUSABLE)
        elif ext_type in _HARMLESS:
            continue
        else:
            # Unknown, potentially transfer-altering extension. Default to refusing: silent
            # wrong numbers are the one thing this library must never produce.
            raise UnsupportedMint(
                f"token carries an unrecognized Token-2022 extension ({ext_type}) that may "
                f"alter transfers; refusing to guess",
                extension=ext_type,
            )

    return MintInfo(decimals=decimals, is_token_2022=True,
                    transfer_fee=fee, extensions=tuple(seen))
