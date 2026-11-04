"""Official USD -> UZS rate of the Central Bank of Uzbekistan (CBU).

The rate is fetched from cbu.uz (aiohttp, 10 s timeout), cached in memory for CACHE_TTL and stored in the
`official_rates` table, so a restart or a CBU outage still has the last good value. A failed fetch only logs
a warning and keeps the last value. `refresh_loop` (started in app.on_startup) refreshes it once at startup and
then every CACHE_TTL. `get_official()` never raises: it returns None only if no rate was ever received.
"""
import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import aiohttp

from utils.db_api.base import session_factory
from utils.db_api.models import OfficialRate

log = logging.getLogger(__name__)

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"
TIMEOUT_SECONDS = 10
CACHE_TTL = timedelta(hours=6)
RETRY_AFTER = timedelta(minutes=5)  # minimum pause between inline retries when there is no rate at all
LOOP_RETRY = timedelta(minutes=30)  # the periodic task's pause after a failed refresh
CURRENCY = "USD"


class RateError(Exception):
    pass


@dataclass(frozen=True)
class OfficialUsd:
    rate: Decimal  # UZS per 1 USD
    day: date  # the date the Central Bank set this rate for


def parse_cbu(payload: Any) -> OfficialUsd:
    """The USD item of the CBU response (`[{"Ccy": "USD", "Rate": "12850.37", "Date": "05.11.2026", ...}]`)."""
    items = payload if isinstance(payload, list) else []
    for item in items:
        if isinstance(item, dict) and str(item.get("Ccy", "")).upper() == CURRENCY:
            try:
                rate = Decimal(str(item["Rate"]).strip().replace(",", "."))
                day = datetime.strptime(str(item["Date"]).strip(), "%d.%m.%Y").date()
            except (KeyError, InvalidOperation, ValueError) as err:
                raise RateError(f"bad USD item: {item!r}") from err
            if not rate.is_finite() or rate <= 0:
                raise RateError(f"bad USD rate: {item['Rate']!r}")
            return OfficialUsd(rate, day)
    raise RateError("no USD item in the CBU response")


async def fetch_cbu() -> OfficialUsd:
    """One request to cbu.uz; raises RateError (or an aiohttp/asyncio error) on any failure."""
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(CBU_URL) as response:
            if response.status != 200:
                raise RateError(f"HTTP {response.status}")
            payload = await response.json(content_type=None)
    return parse_cbu(payload)


class _State:
    value: Optional[OfficialUsd] = None
    fetched_at: Optional[datetime] = None  # naive UTC of the last successful fetch (or of the stored value)
    last_attempt: Optional[datetime] = None
    loaded: bool = False  # the stored value was read from the database


_state = _State()
_lock: Optional[asyncio.Lock] = None


def reset() -> None:
    """Forget the in-memory cache (tests; the stored row stays)."""
    global _lock
    _state.value = _state.fetched_at = _state.last_attempt = None
    _state.loaded = False
    _lock = None


def _utcnow() -> datetime:
    return datetime.utcnow()


async def _load_stored() -> None:
    _state.loaded = True
    async with session_factory() as session:
        row = await session.get(OfficialRate, CURRENCY)
    if row is None:
        return
    try:
        _state.value = OfficialUsd(Decimal(row.rate), row.rate_date)
        _state.fetched_at = row.fetched_at
    except InvalidOperation:
        log.warning("Stored official rate %r is invalid", row.rate)


async def _store(value: OfficialUsd, fetched_at: datetime) -> None:
    async with session_factory() as session, session.begin():
        row = await session.get(OfficialRate, CURRENCY)
        if row is None:
            session.add(OfficialRate(currency=CURRENCY, rate=str(value.rate), rate_date=value.day,
                                     fetched_at=fetched_at))
        else:
            row.rate, row.rate_date, row.fetched_at = str(value.rate), value.day, fetched_at


def _fresh() -> bool:
    return _state.value is not None and _state.fetched_at is not None \
        and _utcnow() - _state.fetched_at < CACHE_TTL


async def refresh() -> Optional[OfficialUsd]:
    """Fetch the rate now. On failure log a warning and keep the last value; returns the current value."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if not _state.loaded:
            with contextlib.suppress(Exception):
                await _load_stored()
        _state.last_attempt = _utcnow()
        try:
            value = await fetch_cbu()
        except Exception as err:  # noqa: BLE001 - network, JSON and parsing errors all mean "keep the old rate"
            log.warning("Could not fetch the CBU rate (%s); keeping %s", err or type(err).__name__,
                        _state.value.rate if _state.value else "none")
            return _state.value
        _state.value, _state.fetched_at = value, _utcnow()
        try:
            await _store(value, _state.fetched_at)
        except Exception:  # noqa: BLE001
            log.warning("Could not store the CBU rate", exc_info=True)
        return value


async def get_official() -> Optional[OfficialUsd]:
    """The current official rate: the in-memory value while fresh, otherwise a refresh; None if never received."""
    if not _state.loaded:
        try:
            await _load_stored()
        except Exception:  # noqa: BLE001
            log.warning("Could not read the stored official rate", exc_info=True)
    if _fresh():
        return _state.value
    # Stale or missing: the periodic task normally refreshes; retry inline only if a rate is missing altogether
    if _state.value is None and (_state.last_attempt is None or _utcnow() - _state.last_attempt >= RETRY_AFTER):
        return await refresh()
    return _state.value


async def refresh_loop() -> None:
    while True:
        try:
            await refresh()
        except Exception:  # noqa: BLE001
            log.exception("CBU rate refresh failed")
        # after a failure try again sooner than in 6 hours
        await asyncio.sleep((CACHE_TTL if _fresh() else LOOP_RETRY).total_seconds())


class Updater:
    """Background task that keeps the rate fresh (started in on_startup, stopped in on_shutdown)."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(refresh_loop())
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


updater = Updater()
