from typing import List, Optional

from sqlalchemy import select

from .base import session_factory
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
