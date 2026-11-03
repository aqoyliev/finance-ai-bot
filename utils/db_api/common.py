from datetime import datetime, timedelta, timezone

# Uzbekistan time (UTC+5, no DST). Datetimes are stored naive in this zone.
TZ = timezone(timedelta(hours=5))

CURRENCIES = ("UZS", "USD")
ACCOUNT_KINDS = ("cash", "debit", "credit")
OPERATION_KINDS = ("expense", "income")


class FinanceError(Exception):
    """Base class for domain errors shown to the user."""


class AccountNotFound(FinanceError):
    pass


class OperationNotFound(FinanceError):
    pass


class CurrencyMismatch(FinanceError):
    def __init__(self, account_currency: str):
        super().__init__(account_currency)
        self.account_currency = account_currency


class SameAccount(FinanceError):
    pass


class InvalidValue(FinanceError):
    pass


def now() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)
