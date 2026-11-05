"""Who may use the bot: roles and the grants managed in the Mini App (Settings -> Users).

- owner: Telegram ids in ADMINS (env). Full access, manages users, never appears in any list or API answer and
  is never stored as a visitor.
- superadmin: ids in SUPERADMINS (env). Uses the bot and manages users; fixed by env, so not listed either.
- user: a row in access_grants, added by an owner / superadmin. A grant added by @username alone is pending
  until that person first writes to the bot (or opens the Mini App); then their id is bound onto it.

Nothing is cached, so a revoke takes effect on the very next update / API request.
"""
import re
from typing import List, Optional

from sqlalchemy import func, or_, select

from data import config

from .base import session_factory
from .common import now
from .models import AccessGrant, Visitor

OWNER, SUPERADMIN, USER = "owner", "superadmin", "user"
MANAGER_ROLES = (OWNER, SUPERADMIN)
VISITOR_LIMIT = 50
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_LINK_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/", re.IGNORECASE)


class AccessError(Exception):
    """Base class of the grant errors below."""


class InvalidUsername(AccessError):
    pass


class AlreadyGranted(AccessError):
    pass


class GrantNotFound(AccessError):
    pass


class VisitorNotFound(AccessError):
    pass


# ---- Roles ----

def owner_ids() -> frozenset:
    return config.ADMIN_IDS


def superadmin_ids() -> frozenset:
    return config.SUPERADMIN_IDS - config.ADMIN_IDS


def manager_ids() -> List[int]:
    """Everybody who manages users (owners first): they get the "somebody wants in" messages."""
    return sorted(owner_ids()) + sorted(superadmin_ids())


def is_fixed(user_id: Optional[int]) -> bool:
    """Owners and superadmins: their access comes from env and is never listed, granted or revoked here."""
    return user_id is not None and (user_id in owner_ids() or user_id in superadmin_ids())


def clean_username(value) -> Optional[str]:
    """'@Name', 'name', 't.me/name' or 'https://t.me/name' -> 'name' (lowercase); None when not a valid one."""
    if not isinstance(value, str):
        return None
    text = _LINK_RE.sub("", value.strip()).lstrip("@").split("?")[0].strip("/ ")
    return text.lower() if USERNAME_RE.match(text) else None


def full_name(first_name: Optional[str], last_name: Optional[str] = None) -> str:
    return " ".join(part for part in ((first_name or "").strip(), (last_name or "").strip()) if part)


async def role_of(user_id: int, username: Optional[str] = None, name: str = "") -> Optional[str]:
    """'owner' | 'superadmin' | 'user' | None. A pending grant for this @username is bound to the id here."""
    if user_id in owner_ids():
        return OWNER
    if user_id in superadmin_ids():
        return SUPERADMIN
    async with session_factory() as session:
        if await session.scalar(select(AccessGrant.id).where(AccessGrant.user_id == user_id)) is not None:
            return USER
    login = (username or "").lower()
    if login and await _bind_pending(user_id, login, name):
        return USER
    return None


async def is_allowed(user_id: int, username: Optional[str] = None, name: str = "") -> bool:
    return await role_of(user_id, username, name) is not None


async def _bind_pending(user_id: int, username: str, name: str) -> bool:
    async with session_factory() as session, session.begin():
        grant = await session.scalar(select(AccessGrant).where(
            AccessGrant.user_id.is_(None), func.lower(AccessGrant.username) == username).limit(1))
        if grant is None:
            return False
        grant.user_id = user_id
        if name:
            grant.display_name = name
    return True


# ---- Grants ----

async def list_grants() -> List[AccessGrant]:
    """Every grant, newest first (owners / superadmins are left out even if a stale row names them)."""
    async with session_factory() as session:
        grants = await session.scalars(select(AccessGrant).order_by(AccessGrant.created_at.desc(),
                                                                    AccessGrant.id.desc()))
        return [g for g in grants if not is_fixed(g.user_id)]


async def count_grants() -> int:
    return len(await list_grants())


async def grant_by_username(username, added_by: int) -> "tuple[AccessGrant, bool]":
    """Grant a @username. Returns (grant, bound): bound is True when a known visitor got the id right away
    (so they can be told). Raises InvalidUsername / AlreadyGranted."""
    login = clean_username(username)
    if login is None:
        raise InvalidUsername()
    async with session_factory() as session, session.begin():
        if await session.scalar(select(AccessGrant.id).where(func.lower(AccessGrant.username) == login)):
            raise AlreadyGranted()
        visitor = await session.scalar(select(Visitor).where(func.lower(Visitor.username) == login)
                                       .order_by(Visitor.last_seen.desc()).limit(1))
        user_id = visitor.user_id if visitor else None
        if is_fixed(user_id):
            raise AlreadyGranted()
        if user_id is not None and await session.scalar(
                select(AccessGrant.id).where(AccessGrant.user_id == user_id)):
            raise AlreadyGranted()
        grant = AccessGrant(user_id=user_id, username=login, added_by=added_by, created_at=now(),
                            display_name=full_name(visitor.first_name, visitor.last_name) if visitor else "")
        session.add(grant)
    return grant, user_id is not None


async def grant_by_id(user_id: int, added_by: int, username: Optional[str] = None,
                      display_name: str = "") -> AccessGrant:
    """Grant a Telegram id (a visitor, a shared contact or the "allow" button). The name / username come from
    the visitor row when known, else from the arguments. A pending grant of the same @username is reused.
    Raises AlreadyGranted (also for owners / superadmins)."""
    if is_fixed(user_id):
        raise AlreadyGranted()
    async with session_factory() as session, session.begin():
        if await session.scalar(select(AccessGrant.id).where(AccessGrant.user_id == user_id)):
            raise AlreadyGranted()
        visitor = await session.get(Visitor, user_id)
        login = ((visitor.username if visitor and visitor.username else username) or "").lower() or None
        name = full_name(visitor.first_name, visitor.last_name) if visitor else ""
        name = name or (display_name or "").strip()
        grant = None
        if login:
            grant = await session.scalar(select(AccessGrant).where(func.lower(AccessGrant.username) == login))
        if grant is not None and grant.user_id is None:
            grant.user_id = user_id
            grant.display_name = name or grant.display_name
        else:
            grant = AccessGrant(user_id=user_id, username=login if grant is None else None, display_name=name,
                                added_by=added_by, created_at=now())
            session.add(grant)
    return grant


async def get_grant(grant_id: int) -> Optional[AccessGrant]:
    async with session_factory() as session:
        return await session.get(AccessGrant, grant_id)


async def revoke(grant_id: int) -> AccessGrant:
    """Delete a grant (effective immediately). Returns the deleted row; raises GrantNotFound."""
    async with session_factory() as session, session.begin():
        grant = await session.get(AccessGrant, grant_id)
        if grant is None or is_fixed(grant.user_id):
            raise GrantNotFound()
        await session.delete(grant)
    return grant


# ---- Visitors ----

async def touch_visitor(user_id: int, username: Optional[str], first_name: Optional[str],
                        last_name: Optional[str] = None, language_code: Optional[str] = None) -> bool:
    """Record / refresh a private-chat user. Owners are never stored. Returns True for a first visit."""
    if user_id in owner_ids():
        return False
    moment = now()
    async with session_factory() as session, session.begin():
        visitor = await session.get(Visitor, user_id)
        created = visitor is None
        if created:
            visitor = Visitor(user_id=user_id, first_seen=moment, notified=False)
            session.add(visitor)
        visitor.username = username or ""
        visitor.first_name = first_name or ""
        visitor.last_name = last_name or ""
        visitor.language_code = language_code or visitor.language_code or ""
        visitor.last_seen = moment
    return created


async def claim_notice(user_id: int) -> bool:
    """True exactly once per visitor: the managers are told about them only the first time."""
    async with session_factory() as session, session.begin():
        visitor = await session.get(Visitor, user_id)
        if visitor is None or visitor.notified:
            return False
        visitor.notified = True
    return True


async def get_visitor(user_id: int) -> Optional[Visitor]:
    if user_id in owner_ids():
        return None
    async with session_factory() as session:
        return await session.get(Visitor, user_id)


async def search_visitors(query: Optional[str] = None, limit: int = VISITOR_LIMIT) -> List[Visitor]:
    """People who wrote to the bot and have no access yet (no owners, superadmins or granted people),
    matching the name / username, newest first."""
    async with session_factory() as session:
        granted = select(AccessGrant.user_id).where(AccessGrant.user_id.is_not(None))
        pending = select(func.lower(AccessGrant.username)).where(AccessGrant.user_id.is_(None),
                                                                 AccessGrant.username.is_not(None))
        hidden = list(owner_ids() | superadmin_ids())
        stmt = select(Visitor).where(Visitor.user_id.not_in(granted),
                                     or_(Visitor.username == "", func.lower(Visitor.username).not_in(pending)))
        if hidden:
            stmt = stmt.where(Visitor.user_id.not_in(hidden))
        text = " ".join((query or "").split()).lstrip("@")
        if text:
            stmt = stmt.where(or_(*(column.icontains(text, autoescape=True) for column in (
                Visitor.username, Visitor.first_name, Visitor.last_name,
                Visitor.first_name + " " + Visitor.last_name))))
        stmt = stmt.order_by(Visitor.last_seen.desc(), Visitor.user_id.desc()).limit(limit)
        return list(await session.scalars(stmt))
