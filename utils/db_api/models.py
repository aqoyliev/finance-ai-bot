from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# All money is stored in minor units (amount * 100) as integers to avoid float errors.


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # Telegram user id
    username: Mapped[str] = mapped_column(String, default="")
    language: Mapped[Optional[str]] = mapped_column(String(2))  # uz | ru | en; None until chosen
    salary_day: Mapped[int] = mapped_column(Integer, default=1)
    base_currency: Mapped[str] = mapped_column(String(3), default="UZS")
    # True once default accounts/categories were created (in the chosen language)
    is_seeded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    # Automatic AI advice (Settings -> AI advice) and the last one handled, so a restart neither skips nor repeats
    advice_weekly: Mapped[bool] = mapped_column(default=True, server_default=true())
    advice_monthly: Mapped[bool] = mapped_column(default=True, server_default=true())
    advice_weekly_sent: Mapped[Optional[date]] = mapped_column(Date)  # the Monday of the last weekly advice
    advice_monthly_sent: Mapped[Optional[date]] = mapped_column(Date)  # start of the period it was sent on


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # cash | debit | credit
    currency: Mapped[str] = mapped_column(String(3), default="UZS")
    # For credit accounts the balance is a negative liability (debt = -balance)
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    # Balance the account was opened with; balance = opening + sum of operation effects
    opening_balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    credit_limit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)  # False = deactivated (soft-deleted)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Mini App: cash | uzcard | humo | visa | mastercard (None for accounts added in the chat)
    card_type: Mapped[Optional[str]] = mapped_column(String(16))
    # Last 4 digits of the card number (never the full number); matched against "*1234" in bank SMS
    last4: Mapped[Optional[str]] = mapped_column(String(4))


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # expense | income


class Subcategory(Base):
    __tablename__ = "subcategories"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Rows of one operation share a group_id: parts of a split purchase or both legs of a transfer
    group_id: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String)  # expense | income | transfer
    # Effect on the account balance: "in" adds the amount, "out" subtracts it
    direction: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)  # always positive
    currency: Mapped[str] = mapped_column(String(3))
    category: Mapped[Optional[str]] = mapped_column(String)
    subcategory: Mapped[Optional[str]] = mapped_column(String)
    note: Mapped[Optional[str]] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, default="manual")  # manual | ai
    # Fingerprint of the AI input (e.g. hash of a bank SMS) used to warn about duplicates
    source_ref: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    from_currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    to_currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate: Mapped[str] = mapped_column(String)  # Decimal as string
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class OfficialRate(Base):
    """Last good default rate (Central Bank of Uzbekistan, else an international market source), one row per currency (USD -> UZS); see utils/rates.py."""
    __tablename__ = "official_rates"

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate: Mapped[str] = mapped_column(String)  # UZS per 1 unit, Decimal as string
    rate_date: Mapped[date] = mapped_column(Date)  # the source's date for the rate (else today in Asia/Tashkent)
    source: Mapped[str] = mapped_column(String, default="cbu", server_default="cbu")  # cbu | market
    fetched_at: Mapped[datetime] = mapped_column(DateTime)  # naive UTC


class Budget(Base):
    """Monthly spending limit of one expense category (the month starts on the user's salary day)."""
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String)  # category name, as stored in Transaction.category
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class AlertSent(Base):
    """A limit alert that was already sent: at most one row per user, subject, threshold and period."""
    __tablename__ = "alerts_sent"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", "threshold", "period_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String)  # budget | credit
    ref: Mapped[str] = mapped_column(String)  # category name (budget) or account id (credit)
    threshold: Mapped[int] = mapped_column(Integer)  # percent: 80 | 100
    period_start: Mapped[date] = mapped_column(Date)  # start of the financial period the alert belongs to
    sent_at: Mapped[datetime] = mapped_column(DateTime)


class AccessGrant(Base):
    """Permission of one regular user, given by an owner / superadmin in the Mini App (see access.py).

    A grant added by @username alone is "pending" (user_id is None) until that person first writes to the bot.
    """
    __tablename__ = "access_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String, index=True)  # lowercase, without "@"
    display_name: Mapped[str] = mapped_column(String, default="", server_default="")
    added_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Visitor(Base):
    """Everybody who wrote to the bot in a private chat (allowed or not), except the owners."""
    __tablename__ = "visitors"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String, default="", server_default="")  # as in Telegram, without "@"
    first_name: Mapped[str] = mapped_column(String, default="", server_default="")
    last_name: Mapped[str] = mapped_column(String, default="", server_default="")
    language_code: Mapped[str] = mapped_column(String, default="", server_default="")  # Telegram client language
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime, index=True)
    notified: Mapped[bool] = mapped_column(default=False, server_default=false())  # managers were told about them
