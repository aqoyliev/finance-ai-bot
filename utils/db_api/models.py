from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
