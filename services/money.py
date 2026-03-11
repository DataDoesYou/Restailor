from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass

@dataclass(frozen=True)
class Money:
    cents: int
    currency: str = "USD"

    @property
    def as_decimal(self) -> Decimal:
        return Decimal(self.cents) / Decimal(100)

    def __str__(self):
        return f"{self.currency} {self.as_decimal:.2f}"

def to_cents(amount: Decimal|float|str, rounding=ROUND_HALF_UP) -> int:
    dec = Decimal(str(amount))
    return int((dec * 100).quantize(Decimal("1"), rounding=rounding))

def from_cents(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)

def format_usd(cents: int) -> str:
    return f"{cents/100:.2f}"
