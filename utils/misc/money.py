from decimal import Decimal, InvalidOperation
from typing import Optional

MAX_AMOUNT = Decimal("1000000000000")  # sanity cap for a single amount


def money_text(minor: int, currency: str) -> str:
    amount = Decimal(minor) / Decimal(100)
    return f"{amount:,.2f} {currency}".replace(",", " ")


def parse_amount(text: str) -> Optional[int]:
    """Parse user input like '12 500,50' into minor units. Returns None if invalid."""
    try:
        value = Decimal(text.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0 or value > MAX_AMOUNT:
        return None
    return int(value * 100)
