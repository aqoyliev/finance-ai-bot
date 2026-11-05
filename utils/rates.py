"""Default USD -> UZS rate: the Central Bank of Uzbekistan (CBU) with international fallbacks.

The rate is fetched through a chain: cbu.uz (5 s timeout; geo-blocked outside Uzbekistan), then open.er-api.com and
the jsdelivr currency-api (10 s each, source "market"). Every value must be a finite number in (1000, 100000).
It is cached in memory for CACHE_TTL and stored in the `official_rates` table together with its source, so a restart
or an outage still has the last good value. A failed fetch only logs a warning and keeps the last value. `refresh_loop` (started in app.on_startup) refreshes it once at startup and
then every CACHE_TTL. `get_official()` never raises: it returns None only if no rate was ever received.
"""
import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import aiohttp

from utils.db_api.base import session_factory
from utils.db_api.models import OfficialRate

log = logging.getLogger(__name__)

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"
ER_API_URL = "https://open.er-api.com/v6/latest/USD"
CURRENCY_API_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"
CBU_TIMEOUT = 5
TIMEOUT_SECONDS = 10  # the fallbacks
USER_AGENT = "finance-ai-bot"
MIN_RATE, MAX_RATE = Decimal(1000), Decimal(100000)  # sanity bounds (exclusive) for UZS per 1 USD
SOURCE_CBU, SOURCE_MARKET = "cbu", "market"
TASHKENT = ZoneInfo("Asia/Tashkent")
CACHE_TTL = timedelta(hours=6)
RETRY_AFTER = timedelta(minutes=5)  # minimum pause between inline retries when there is no rate at all
LOOP_RETRY = timedelta(minutes=30)  # the periodic task's pause after a failed refresh
CURRENCY = "USD"


class RateError(Exception):
    pass


@dataclass(frozen=True)
class OfficialUsd:
    rate: Decimal  # UZS per 1 USD
    day: date  # the date the source gave for this rate (otherwise today in Asia/Tashkent)
    source: str = SOURCE_CBU  # "cbu" (official) | "market" (international fallback)


def today_tashkent() -> date:
    return datetime.now(TASHKENT).date()


def check_rate(value: Any) -> Decimal:
    """A finite number with MIN_RATE < rate < MAX_RATE, otherwise RateError."""
    if isinstance(value, bool):
        raise RateError(f"bad rate: {value!r}")
    try:
        rate = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation as err:
        raise RateError(f"bad rate: {value!r}") from err
    if not rate.is_finite() or not MIN_RATE < rate < MAX_RATE:
        raise RateError(f"rate out of range: {value!r}")
    return rate


def parse_cbu(payload: Any) -> OfficialUsd:
    """The USD item of the CBU response (`[{"Ccy": "USD", "Rate": "12850.37", "Date": "05.11.2026", ...}]`)."""
    items = payload if isinstance(payload, list) else []
    for item in items:
        if isinstance(item, dict) and str(item.get("Ccy", "")).upper() == CURRENCY:
            try:
                rate = check_rate(item["Rate"])
                day = datetime.strptime(str(item["Date"]).strip(), "%d.%m.%Y").date()
            except (KeyError, ValueError) as err:
                raise RateError(f"bad USD item: {item!r}") from err
            return OfficialUsd(rate, day, SOURCE_CBU)
    raise RateError("no USD item in the CBU response")


def parse_er_api(payload: Any) -> OfficialUsd:
    """open.er-api.com: `{"result": "success", "rates": {"UZS": 11910.62}, "time_last_update_utc": "Wed, 04 Nov 2026 ..."}`."""
    if not isinstance(payload, dict) or payload.get("result") != "success" or not isinstance(payload.get("rates"), dict):
        raise RateError("bad er-api response")
    rate = check_rate(payload["rates"].get("UZS"))
    day = None
    with contextlib.suppress(KeyError, TypeError, ValueError):
        day = parsedate_to_datetime(str(payload["time_last_update_utc"])).date()
    return OfficialUsd(rate, day or today_tashkent(), SOURCE_MARKET)


def parse_currency_api(payload: Any) -> OfficialUsd:
    """jsdelivr currency-api: `{"date": "2026-11-05", "usd": {"uzs": 11885.05}}`."""
    if not isinstance(payload, dict) or not isinstance(payload.get("usd"), dict):
        raise RateError("bad currency-api response")
    rate = check_rate(payload["usd"].get("uzs"))
    day = None
    with contextlib.suppress(KeyError, TypeError, ValueError):
        day = date.fromisoformat(str(payload["date"]).strip())
    return OfficialUsd(rate, day or today_tashkent(), SOURCE_MARKET)


async def _get_json(url: str, timeout_seconds: float) -> Any:
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": USER_AGENT}) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise RateError(f"HTTP {response.status}")
            return await response.json(content_type=None)


async def fetch_cbu() -> OfficialUsd:
    """One request to cbu.uz; raises RateError (or an aiohttp/asyncio error) on any failure."""
    return parse_cbu(await _get_json(CBU_URL, CBU_TIMEOUT))


async def fetch_er_api() -> OfficialUsd:
    return parse_er_api(await _get_json(ER_API_URL, TIMEOUT_SECONDS))


async def fetch_currency_api() -> OfficialUsd:
    return parse_currency_api(await _get_json(CURRENCY_API_URL, TIMEOUT_SECONDS))


def _chain() -> List[Tuple[str, Callable[[], Awaitable[OfficialUsd]]]]:
    # looked up at call time so tests can replace the individual fetchers
    return [("cbu.uz", fetch_cbu), ("open.er-api.com", fetch_er_api), ("currency-api", fetch_currency_api)]


async def fetch_official() -> OfficialUsd:
    """The first source of the chain that answers with a valid value; RateError if all of them fail."""
    errors = []
    for name, fetch in _chain():
        try:
            return await fetch()
        except Exception as err:  # noqa: BLE001 - timeouts, network, JSON and validation errors: try the next source
            errors.append(f"{name}: {err or type(err).__name__}")
            log.warning("Rate source %s failed: %s", name, err or type(err).__name__)
    raise RateError("all rate sources failed (" + "; ".join(errors) + ")")


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
        _state.value = OfficialUsd(Decimal(row.rate), row.rate_date, row.source or SOURCE_CBU)
        _state.fetched_at = row.fetched_at
    except InvalidOperation:
        log.warning("Stored official rate %r is invalid", row.rate)


async def _store(value: OfficialUsd, fetched_at: datetime) -> None:
    async with session_factory() as session, session.begin():
        row = await session.get(OfficialRate, CURRENCY)
        if row is None:
            session.add(OfficialRate(currency=CURRENCY, rate=str(value.rate), rate_date=value.day,
                                     source=value.source, fetched_at=fetched_at))
        else:
            row.rate, row.rate_date, row.source, row.fetched_at = str(value.rate), value.day, value.source, fetched_at


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
            value = await fetch_official()
        except Exception as err:  # noqa: BLE001 - network, JSON and parsing errors all mean "keep the old rate"
            log.warning("Could not fetch the USD rate (%s); keeping %s", err or type(err).__name__,
                        _state.value.rate if _state.value else "none")
            return _state.value
        _state.value, _state.fetched_at = value, _utcnow()
        try:
            await _store(value, _state.fetched_at)
        except Exception:  # noqa: BLE001
            log.warning("Could not store the USD rate", exc_info=True)
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
            log.exception("USD rate refresh failed")
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
