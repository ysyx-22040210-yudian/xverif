from __future__ import annotations

from dataclasses import dataclass

from .errors import FourStateUnsupported, WidthError


def _mask(width: int) -> int:
    if width <= 0:
        raise WidthError("width must be positive", width=width)
    return (1 << width) - 1


def _group4(bits: str) -> str:
    rev = bits[::-1]
    groups = [rev[i : i + 4][::-1] for i in range(0, len(rev), 4)]
    return "_".join(reversed(groups))


@dataclass(frozen=True)
class BitVector:
    width: int
    value: int
    signed: bool = False
    state: str = "2state"
    x_mask: int = 0
    z_mask: int = 0

    def __post_init__(self):
        if self.width <= 0:
            raise WidthError("width must be positive", width=self.width)
        if self.state not in {"2state", "4state"}:
            raise WidthError("state must be 2state or 4state", state=self.state)
        mask = _mask(self.width)
        object.__setattr__(self, "value", self.value & mask)
        object.__setattr__(self, "x_mask", self.x_mask & mask)
        object.__setattr__(self, "z_mask", self.z_mask & mask)
        if self.state == "2state" and (self.x_mask or self.z_mask):
            raise FourStateUnsupported("2-state value cannot contain x/z bits")

    @classmethod
    def from_int(cls, value: int, width: int | None = None, signed: bool = False) -> "BitVector":
        if width is None:
            if value < 0:
                width = max(32, (-value).bit_length() + 1)
            else:
                width = max(32, value.bit_length() or 1)
        return cls(width=width, value=value, signed=signed)

    @classmethod
    def bool(cls, value: bool) -> "BitVector":
        return cls(width=1, value=1 if value else 0)

    @property
    def unknown_mask(self) -> int:
        return self.x_mask | self.z_mask

    @property
    def known(self) -> bool:
        return self.unknown_mask == 0

    @property
    def unsigned(self) -> int | None:
        return None if not self.known else self.value

    @property
    def signed_value(self) -> int | None:
        if not self.known:
            return None
        sign_bit = 1 << (self.width - 1)
        if self.value & sign_bit:
            return self.value - (1 << self.width)
        return self.value

    def require_known(self, op: str = "operation") -> None:
        if not self.known:
            raise FourStateUnsupported(f"{op} does not support x/z bits", op=op)

    def truthy(self) -> bool:
        self.require_known("logical evaluation")
        return self.value != 0

    def as_int(self, prefer_signed: bool = False) -> int:
        self.require_known("integer conversion")
        if prefer_signed or self.signed:
            assert self.signed_value is not None
            return self.signed_value
        return self.value

    def with_signed(self, signed: bool) -> "BitVector":
        return BitVector(self.width, self.value, signed=signed, state=self.state, x_mask=self.x_mask, z_mask=self.z_mask)

    def resize(self, width: int, *, signed_extend: bool = False, signed: bool | None = None) -> "BitVector":
        if width <= 0:
            raise WidthError("target width must be positive", width=width)
        value = self.value
        x_mask = self.x_mask
        z_mask = self.z_mask
        if width > self.width and signed_extend and self.width > 0:
            high = ((1 << (width - self.width)) - 1) << self.width
            sign = 1 << (self.width - 1)
            if self.x_mask & sign:
                x_mask |= high
            elif self.z_mask & sign:
                z_mask |= high
            elif self.value & sign:
                value |= high
        mask = _mask(width)
        return BitVector(
            width,
            value & mask,
            signed=self.signed if signed is None else signed,
            state=self.state,
            x_mask=x_mask & mask,
            z_mask=z_mask & mask,
        )

    def to_bin_digits(self) -> str:
        chars = []
        for bit in range(self.width - 1, -1, -1):
            bit_mask = 1 << bit
            if self.x_mask & bit_mask:
                chars.append("x")
            elif self.z_mask & bit_mask:
                chars.append("z")
            else:
                chars.append("1" if self.value & bit_mask else "0")
        return "".join(chars)

    def to_bin(self) -> str:
        return _group4(self.to_bin_digits())

    def to_hex_digits(self) -> str:
        digits = []
        groups = (self.width + 3) // 4
        for idx in range(groups - 1, -1, -1):
            shift = idx * 4
            nibble_mask = 0xF << shift
            x = (self.x_mask & nibble_mask) >> shift
            z = (self.z_mask & nibble_mask) >> shift
            val = (self.value & nibble_mask) >> shift
            if x and not z and x == 0xF:
                digits.append("x")
            elif z and not x and z == 0xF:
                digits.append("z")
            elif x or z:
                digits.append("?")
            else:
                digits.append(format(val, "x"))
        return "".join(digits).lstrip("0") or "0"

    def to_sv(self, base: str = "h") -> str:
        signed = "s" if self.signed else ""
        if base == "b":
            return f"{self.width}'{signed}b{self.to_bin_digits()}"
        if base == "d":
            if self.known:
                return f"{self.width}'{signed}d{self.as_int(self.signed)}"
            return f"{self.width}'{signed}b{self.to_bin_digits()}"
        return f"{self.width}'{signed}h{self.to_hex_digits()}"

    def to_result(self) -> dict:
        result = {
            "width": self.width,
            "signed": self.signed,
            "known": self.known,
            "unsigned": self.unsigned,
            "signed_value": self.signed_value,
            "hex": f"0x{self.to_hex_digits()}",
            "bin": self.to_bin(),
            "sv": self.to_sv("h"),
        }
        if self.unknown_mask:
            result["x_mask"] = f"0x{BitVector(self.width, self.x_mask).to_hex_digits()}"
            result["z_mask"] = f"0x{BitVector(self.width, self.z_mask).to_hex_digits()}"
        return result

    def __str__(self) -> str:
        return self.to_sv("h")
