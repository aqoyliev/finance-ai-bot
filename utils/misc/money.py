from decimal import Decimal, InvalidOperation
from typing import Optional

MAX_AMOUNT = Decimal("1000000000000")  # sanity cap for a single amount


def money_text(minor: int, currency: str) -> str:
    amount = Decimal(minor) / Decimal(100)
    return f"{amount:,.2f} {currency}".replace(",", " ")


def short_money(minor: int) -> str:
    """Compact amount for chart labels: 1 250 000 -> '1.25M'."""
    value = Decimal(minor) / Decimal(100)
    for limit, suffix in ((Decimal(10) ** 9, "B"), (Decimal(10) ** 6, "M"), (Decimal(10) ** 3, "K")):
        if abs(value) >= limit:
            return f"{(value / limit):.2f}".rstrip("0").rstrip(".") + suffix
    return f"{value:.0f}"


def parse_amount(text: str, allow_zero: bool = False) -> Optional[int]:
    """Parse user input like '12 500,50' into minor units. Returns None if invalid."""
    try:
        value = Decimal((text or "").replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > MAX_AMOUNT or (value == 0 and not allow_zero):
        return None
    return int(value * 100)
