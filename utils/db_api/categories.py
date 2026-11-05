from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from .base import session_factory
from .defaults import FALLBACK_CATEGORIES
from .models import Category, Subcategory


async def list_categories(user_id: int, kind: str) -> List[Category]:
    async with session_factory() as session:
        result = await session.scalars(
            select(Category).where(Category.user_id == user_id, Category.kind == kind).order_by(Category.id))
        return list(result)


async def get_category(user_id: int, category_id: int) -> Optional[Category]:
    async with session_factory() as session:
        return await session.scalar(
            select(Category).where(Category.id == category_id, Category.user_id == user_id))


async def list_subcategories(category_id: int) -> List[Subcategory]:
    async with session_factory() as session:
        result = await session.scalars(
            select(Subcategory).where(Subcategory.category_id == category_id).order_by(Subcategory.id))
        return list(result)


async def get_subcategory(user_id: int, subcategory_id: int) -> Optional[Subcategory]:
    async with session_factory() as session:
        return await session.scalar(
            select(Subcategory).join(Category, Category.id == Subcategory.category_id)
            .where(Subcategory.id == subcategory_id, Category.user_id == user_id))


async def category_tree(user_id: int) -> Dict[str, List[Tuple[str, List[str]]]]:
    """Every category of the user with its subcategory names: {"expense": [(name, [subs])], "income": [...]}."""
    async with session_factory() as session:
        categories = list(await session.scalars(
            select(Category).where(Category.user_id == user_id).order_by(Category.id)))
        subs = (await session.execute(
            select(Subcategory.category_id, Subcategory.name)
            .where(Subcategory.category_id.in_([c.id for c in categories])).order_by(Subcategory.id))).all()
    by_category: Dict[int, List[str]] = {}
    for category_id, name in subs:
        by_category.setdefault(category_id, []).append(name)
    tree: Dict[str, List[Tuple[str, List[str]]]] = {"expense": [], "income": []}
    for category in categories:
        tree.setdefault(category.kind, []).append((category.name, by_category.get(category.id, [])))
    return tree


async def fallback_category(user_id: int, kind: str, lang: str) -> str:
    """Name of the "Other" category of `kind` ("Boshqa" / "Прочее" / "Other"), created if the user has none."""
    names = FALLBACK_CATEGORIES[kind]
    wanted = [names.get(lang, names["en"])] + list(names.values())
    existing = {c.name.casefold(): c.name for c in await list_categories(user_id, kind)}
    for name in wanted:
        if name.casefold() in existing:
            return existing[name.casefold()]
    async with session_factory() as session, session.begin():
        session.add(Category(user_id=user_id, name=wanted[0], kind=kind))
    return wanted[0]
