"""Money as a first-class value: integer minor units, explicit currency.

Floats are banned here.  ``109999.99`` cannot be represented exactly in
binary floating point, and a transaction engine that compares an authorized
ceiling against a checkout total cannot afford a half-paisa of drift.  Every
amount is an integer count of the currency's smallest unit plus an ISO-4217
code, and arithmetic between different currencies raises rather than guesses.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

__all__ = ["MINOR_UNITS", "CurrencyMismatch", "Money"]

# Exponent per ISO-4217 code.  Most currencies are 2; the zero-decimal ones
# below would silently inflate amounts 100x if assumed to be 2.
MINOR_UNITS: dict[str, int] = {
    "INR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AUD": 2,
    "CAD": 2,
    "SGD": 2,
    "AED": 2,
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "CLP": 0,
    "ISK": 0,
    "BHD": 3,
    "KWD": 3,
    "OMR": 3,
    "JOD": 3,
    "TND": 3,
}

_SYMBOLS: dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}


class CurrencyMismatch(ValueError):
    """Raised when two amounts in different currencies are combined."""

    def __init__(self, left: str, right: str) -> None:
        super().__init__(
            f"cannot combine {left} with {right}; convert explicitly with a "
            "rate that carries its own provenance"
        )


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """An exact amount.  ``minor`` is e.g. paise for INR, cents for USD."""

    minor: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.minor, int) or isinstance(self.minor, bool):
            raise TypeError("Money.minor must be an int (minor units, not a float)")
        code = self.currency.upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError(
                f"currency must be a 3-letter ISO-4217 code, got {self.currency!r}"
            )
        object.__setattr__(self, "currency", code)

    # --- constructors ---------------------------------------------------

    @classmethod
    def of(cls, major: str | int | Decimal, currency: str) -> Money:
        """Build from a major-unit value: ``Money.of("1099.99", "INR")``.

        Pass strings or Decimals.  A float is rejected, because the caller
        has already lost precision by the time we see it.
        """
        if isinstance(major, float):
            raise TypeError(
                "refusing a float amount; pass a str or Decimal so the value is exact"
            )
        code = currency.upper()
        exponent = MINOR_UNITS.get(code, 2)
        scaled = (Decimal(major) * (10**exponent)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return cls(int(scaled), code)

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(0, currency)

    # --- properties -----------------------------------------------------

    @property
    def exponent(self) -> int:
        return MINOR_UNITS.get(self.currency, 2)

    @property
    def major(self) -> Decimal:
        """The amount in major units, exact."""
        # scaleb rather than division: it shifts the exponent without going
        # through __truediv__, so the result stays exact and typed.
        return Decimal(self.minor).scaleb(-self.exponent)

    # --- arithmetic -----------------------------------------------------

    def _same(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(self.currency, other.currency)

    def __add__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor - other.minor, self.currency)

    def __mul__(self, factor: int) -> Money:
        if not isinstance(factor, int) or isinstance(factor, bool):
            raise TypeError("Money may only be multiplied by an int quantity")
        return Money(self.minor * factor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.minor, self.currency)

    # --- comparison -----------------------------------------------------

    def __lt__(self, other: Money) -> bool:
        self._same(other)
        return self.minor < other.minor

    def __le__(self, other: Money) -> bool:
        self._same(other)
        return self.minor <= other.minor

    def __gt__(self, other: Money) -> bool:
        self._same(other)
        return self.minor > other.minor

    def __ge__(self, other: Money) -> bool:
        self._same(other)
        return self.minor >= other.minor

    # --- presentation ---------------------------------------------------

    def __str__(self) -> str:
        symbol = _SYMBOLS.get(self.currency, self.currency + " ")
        return f"{symbol}{self.major:,.{self.exponent}f}"

    def __repr__(self) -> str:
        return f"Money.of('{self.major}', '{self.currency}')"

    def to_dict(self) -> dict[str, Any]:
        """Serialized as minor units, never as a float."""
        return {
            "minor": self.minor,
            "currency": self.currency,
            "display": str(self),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Money:
        return cls(int(raw["minor"]), str(raw["currency"]))
