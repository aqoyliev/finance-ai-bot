from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import session_factory
from .common import InvalidValue, now
from .defaults import DEFAULT_ACCOUNTS, DEFAULT_CATEGORIES, INCOME_CATEGORIES
from .models import Account, Category, ExchangeRate, Subcategory, User


async def get_user(user_id: int) -> Optional[User]:
    async with session_factory() as session:
        return await session.get(User, user_id)


async def get_language(user_id: int) -> Optional[str]:
    user = await get_user(user_id)
    return user.language if user else None


async def _seed_defaults(session: AsyncSession, user: User, lang: str) -> None:
    """Create starter accounts and categories named in the given language."""
    created_at = now()
    for name, kind, currency in DEFAULT_ACCOUNTS[lang]:
        session.add(Account(user_id=user.id, name=name, kind=kind, currency=currency, created_at=created_at))

    for name, subs in DEFAULT_CATEGORIES[lang].items():
        category = Category(user_id=user.id, name=name, kind="expense")
        session.add(category)
        await session.flush()
        session.add_all(Subcategory(category_id=category.id, name=sub) for sub in subs)
    session.add_all(Category(user_id=user.id, name=name, kind="income") for name in INCOME_CATEGORIES[lang])
    user.is_seeded = True


async def set_language(user_id: int, username: Optional[str], lang: str) -> bool:
    """Store the language, creating and seeding the user on first choice. Returns True if seeded now."""
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        if user is None:
            user = User(id=user_id, username=username or "", created_at=now())
            session.add(user)
        user.language = lang
        if user.is_seeded:
            return False
        await _seed_defaults(session, user, lang)
        return True


async def set_salary_day(user_id: int, day: int) -> None:
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        user.salary_day = day


async def set_usd_rate(user_id: int, rate: Decimal) -> None:
    """Store USD->UZS and the inverse UZS->USD rate."""
    updated_at = now()
    async with session_factory() as session, session.begin():
        for from_cur, to_cur, value in (("USD", "UZS", rate), ("UZS", "USD", Decimal(1) / rate)):
            row = await session.get(ExchangeRate, (user_id, from_cur, to_cur))
            if row is None:
                session.add(ExchangeRate(user_id=user_id, from_currency=from_cur, to_currency=to_cur,
                                         rate=str(value), updated_at=updated_at))
            else:
                row.rate = str(value)
                row.updated_at = updated_at


# ---- Automatic AI advice ----

ADVICE_KINDS = ("weekly", "monthly")


async def list_users() -> List[User]:
    """Users who finished the first /start (language chosen)."""
    async with session_factory() as session:
        return list(await session.scalars(select(User).where(User.language.is_not(None)).order_by(User.id)))


async def toggle_advice(user_id: int, kind: str) -> User:
    """Switch weekly / monthly advice on or off; returns the updated user."""
    if kind not in ADVICE_KINDS:
        raise InvalidValue()
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        setattr(user, f"advice_{kind}", not getattr(user, f"advice_{kind}"))
        return user


async def mark_advice_sent(user_id: int, kind: str, day: date) -> None:
    """Remember that the weekly (day = that Monday) or monthly (day = period start) advice was handled."""
    if kind not in ADVICE_KINDS:
        raise InvalidValue()
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        setattr(user, f"advice_{kind}_sent", day)
