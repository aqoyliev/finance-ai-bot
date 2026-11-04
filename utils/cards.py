"""Receipt-style report cards (weekly, monthly, period report) rendered from HTML to PNG by headless Chromium.

Three layers:
- load_*(): read the figures of a window from the database into a CardData (async, no rendering);
- build_view(): turn a CardData into a plain view-model (dicts and strings, every label localized) - pure, so it
  is tested without a browser;
- render_html() + CardRenderer: Jinja2 templates in templates/cards/ and one shared Playwright Chromium that
  screenshots the full page. The browser is launched lazily on the first card, reused, and closed by
  app.on_shutdown (close_renderer).

Rendering never raises to the caller: the *_card() helpers return None when Chromium is missing, crashes or times
out, so handlers fall back to the matplotlib chart (utils/charts.py) or to text only.
Docker: the image needs `playwright install --with-deps chromium` after `pip install -r requirements.txt`.

Money: amounts are minor units; UZS is shown in whole sum, USD with cents ("$1 240.50"). Thousands are grouped
with U+202F (narrow no-break space) and negatives use U+2212. Currencies are never converted: with expenses in
both, every currency gets its own section.
"""
import asyncio
import base64
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from utils.db_api import finance as db
from utils.db_api import reports as rep
from utils.i18n import t

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates" / "cards"
FONTS = ROOT / "assets" / "fonts"
FONT_FILES = {400: "JetBrainsMono-Regular.woff2", 500: "JetBrainsMono-Medium.woff2",
              700: "JetBrainsMono-Bold.woff2", 800: "JetBrainsMono-ExtraBold.woff2"}

NNBSP = " "  # thousands separator
MINUS = "−"
UZ_APOSTROPHE = re.compile(r"([OoGg])['`‘’ʻ]|['`’ʼ](?=\w)")  # typed oʻ / gʻ, and tutuq belgisi
WIDTH = 1080  # card (viewport) width in CSS pixels; the height follows the content
BAR_HEIGHT = 130  # px of the tallest barcode bar
ASCII_WIDTH = 10  # budget / credit bars: [#######---]
SHARE_WIDTH = 20  # report share bars: ████░░░░
ROW_LIMITS = {"weekly": 6, "monthly": 8, "report": 8}  # category rows; the rest is folded into "Other"
TOP_EXPENSES = 3
MAX_BUDGET_ROWS = 6
MAX_NAME = 48  # characters; CSS also ends a long name with an ellipsis
PAY_KINDS = ("cash", "debit", "credit")
RENDER_TIMEOUT = 25  # seconds for one card, browser start included
RETRY_LAUNCH_AFTER = 300  # seconds to wait after Chromium failed to start before trying again
MAX_PAGES = 2  # cards rendered at the same time

_bot_username = ""


def set_bot_username(username: Optional[str]) -> None:
    """The @username printed in the card footer (app.on_startup sets it; empty = no username)."""
    global _bot_username
    _bot_username = username or ""


# ---- Input ----

@dataclass
class CardData:
    """Figures of one card window. Ends are exclusive."""
    kind: str  # weekly | monthly | report
    start: date
    end: date
    compare_start: date
    compare_end: date
    current: db.RangeSummary
    previous: db.RangeSummary
    rows: List[db.ExpenseRow] = field(default_factory=list)  # expense rows of the window, oldest first
    budgets: List[db.BudgetUsage] = field(default_factory=list)
    credit: List[Tuple[str, int, int]] = field(default_factory=list)  # (currency, debt, limit) per credit card
    through: Optional[date] = None  # last day shown (default: end - 1)
    partial: bool = False  # a running period compared with the same number of days

    @property
    def last_day(self) -> date:
        return self.through or self.end - timedelta(days=1)

    def spent_currencies(self) -> List[str]:
        return [c for c in db.CURRENCIES if self.current.total("expense", c) > 0]


# ---- Formatting (pure) ----

def _half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def group(number: int) -> str:
    """12440000 -> '12 440 000' (U+202F), negatives with U+2212."""
    text = f"{abs(number):,}".replace(",", NNBSP)
    return MINUS + text if number < 0 else text


def money(minor: int, currency: str, sign: bool = False) -> str:
    """UZS in whole sum ('3 860 000'), USD with cents ('$1 240.50'); sign=True adds '+' to positive amounts."""
    value = Decimal(abs(minor)) / 100
    if currency == "USD":
        body = "$" + f"{value:,.2f}".replace(",", NNBSP)
    else:
        body = group(_half_up(value))
        if currency != "UZS":
            body = f"{body} {currency}"
    if minor < 0:
        return MINUS + body
    return ("+" + body) if sign and minor > 0 else body


def decimal_text(value: float, lang: str, digits: int = 1) -> str:
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if lang in ("uz", "ru") else text


def unit_value(minor: int, currency: str) -> str:
    """Barcode label: thousands of sum for UZS, whole dollars for USD."""
    if currency == "UZS":
        return group(_half_up(Decimal(minor) / 100_000))
    return group(_half_up(Decimal(minor) / 100))


def plural(key: str, n: int, lang: str) -> str:
    """card_<key>_one / _few / _many by the language's plural rules (only Russian has three forms)."""
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            form = "one"
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            form = "few"
        else:
            form = "many"
    else:
        form = "one" if n == 1 else "many"
    return t(f"card_{key}_{form}", lang, _escape=False, n=n)


def uzbek_letters(text: str) -> str:
    """O' / G' typed with an ASCII apostrophe -> Oʻ / Gʻ (U+02BB), any other apostrophe -> ʼ (U+02BC)."""
    return UZ_APOSTROPHE.sub(lambda m: m.group(1) + "ʻ" if m.group(1) else "ʼ", text)


def clean_name(text: Optional[str], upper: bool = True, lang: str = "") -> str:
    """User text for the card: emoji and control characters dropped, spaces collapsed, capped at MAX_NAME;
    Uzbek apostrophes are typeset (see uzbek_letters)."""
    kept = []
    for ch in text or "":
        code = ord(ch)
        if code >= 0x1F000 or code in (0x200D, 0xFE0E, 0xFE0F) or 0x2600 <= code <= 0x27BF:
            continue
        if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn", "So"):
            continue
        kept.append(ch)
    name = " ".join("".join(kept).split()) or rep.NO_CATEGORY
    if lang == "uz":
        name = uzbek_letters(name)
    if len(name) > MAX_NAME:
        name = name[:MAX_NAME - 1].rstrip() + "…"
    return name.upper() if upper else name


def change_badge(current: int, previous: int, lang: str) -> Optional[dict]:
    """'▲ 18%' (red, spent more) / '▼ 6%' (blue, less) / 'new' when there was nothing before."""
    if previous <= 0:
        return {"text": t("report_new", lang, _escape=False), "tone": "mute"} if current > 0 else None
    percent = rep.change_percent(current, previous)
    if percent > 0:
        return {"text": f"▲ {percent}%", "tone": "up"}
    if percent < 0:
        return {"text": f"▼ {-percent}%", "tone": "dn"}
    return {"text": "0%", "tone": "mute"}


def stamp(current: int, previous: int, lang: str) -> Optional[dict]:
    """The rubber stamp with the change of total spending; None when there is nothing to compare with."""
    if previous <= 0:
        return None
    exact = (current - previous) * 100 / previous
    size = abs(exact)
    number = group(_half_up(Decimal(size))) if size >= 100 else decimal_text(size, lang)
    if round(exact, 1) == 0:
        return {"main": f"= {decimal_text(0, lang)}%", "sub": t("card_same", lang, _escape=False).upper(),
                "tone": "ink"}
    if exact > 0:
        return {"main": f"▲ {number}%", "sub": t("card_more", lang, _escape=False).upper(), "tone": "up"}
    return {"main": f"▼ {number}%", "sub": t("card_less", lang, _escape=False).upper(), "tone": "dn"}


# ---- View-model pieces (pure) ----

def fold_categories(items: Sequence[Tuple[str, int, int]], limit: int,
                    other: str) -> List[Tuple[str, int, int]]:
    """(name, amount, previous) biggest first; beyond `limit` rows the tail (and any category already named like
    `other`) is summed into one `other` row, shown last."""
    ordered = sorted((i for i in items if i[1] > 0), key=lambda i: (-i[1], i[0]))
    if len(ordered) <= limit:
        return ordered
    folded_name = other.casefold()
    named = [i for i in ordered if i[0].casefold() != folded_name]
    keep = named[:limit - 1]
    tail = [i for i in ordered if i not in keep]
    return keep + [(other, sum(i[1] for i in tail), sum(i[2] for i in tail))]


def bar_heights(values: Sequence[int]) -> List[dict]:
    """Barcode bars: height = value / max * BAR_HEIGHT px; the first biggest bar is highlighted."""
    top = max(values, default=0)
    if top <= 0:
        return [{"h": 0, "hi": False} for _ in values]
    peak = list(values).index(top)
    return [{"h": _half_up(Decimal(max(v, 0)) * BAR_HEIGHT / top), "hi": i == peak} for i, v in enumerate(values)]


def ascii_bar(used: int, limit: int) -> str:
    """[#########-]: ceil(used% / 10) marks, at most ASCII_WIDTH."""
    marks = min(ASCII_WIDTH, -(-max(used, 0) * ASCII_WIDTH // limit)) if limit > 0 else 0
    return "[" + "#" * marks + "-" * (ASCII_WIDTH - marks) + "]"


def share_bar(amount: int, largest: int) -> str:
    """████████░░░░: SHARE_WIDTH cells relative to the largest category (at least one for any spending)."""
    if largest <= 0:
        return "░" * SHARE_WIDTH
    cells = min(SHARE_WIDTH, (amount * SHARE_WIDTH * 2 + largest) // (largest * 2))
    if amount > 0:
        cells = max(cells, 1)
    return "█" * cells + "░" * (SHARE_WIDTH - cells)


def _labels(lang: str) -> dict:
    def label(key: str) -> str:
        return t(key, lang, _escape=False).upper()

    return {
        "categories": label("card_categories"), "total": label("card_total"), "biggest": label("card_biggest"),
        "biggest_list": label("card_biggest_list"), "budgets": label("card_budgets"),
        "over_budget": label("card_over_budget"), "income": label("card_income"), "expense": label("card_expense"),
        "balance": label("card_balance"), "payment": label("card_payment"), "credit_limit": label("card_credit_limit"),
        "mixed_note": t("card_mixed_note", lang, _escape=False),
    }


def _prev_label(data: CardData, lang: str) -> str:
    if data.kind == "weekly":
        key = "card_prev_week"
    elif data.kind == "monthly":
        key = "card_prev_month"
    elif data.partial:
        days = plural("days", (data.compare_end - data.compare_start).days, lang)
        return t("card_prev_same_days", lang, _escape=False, days=days).upper()
    else:
        key = "card_prev_period"
    return t(key, lang, _escape=False).upper()


def _buckets(data: CardData, currency: str, lang: str) -> dict:
    """Barcode of a currency: spending per day (weekly) or per 7-day chunk of the period (monthly)."""
    unit = t(f"card_unit_{currency}", lang, _escape=False)
    days = max((data.end - data.start).days, 1)
    if data.kind == "weekly":
        names = t("card_weekdays", lang, _escape=False).split()
        values = [0] * days
        labels = [names[(data.start + timedelta(days=i)).weekday()] for i in range(days)]
        title = t("card_by_day", lang, _escape=False, unit=unit)
        size = 1
    else:
        size = 7
        chunks = -(-days // size)
        values = [0] * chunks
        labels = []
        for i in range(chunks):
            length = min(size, days - i * size)
            labels.append(t("card_week_n", lang, _escape=False, n=i + 1) if length == size
                          else plural("days", length, lang))
        title = t("card_by_week", lang, _escape=False, unit=unit)
    for row in data.rows:
        if row.currency == currency:
            index = (row.occurred_at.date() - data.start).days // size
            if 0 <= index < len(values):
                values[index] += row.amount_minor
    bars = bar_heights(values)
    for bar, label, value in zip(bars, labels, values):
        bar.update(label=label, value=unit_value(value, currency))
    return {"title": title, "bars": bars}


def _sections(data: CardData, lang: str) -> List[dict]:
    other = t("report_chart_other", lang, _escape=False)
    mixed = len(data.spent_currencies()) > 1
    result = []
    for currency in data.spent_currencies():
        expense = data.current.total("expense", currency)
        previous = data.previous.total("expense", currency)
        items = [(name, amount, data.previous.expense_by_category.get((currency, name), 0))
                 for (cur, name), amount in data.current.expense_by_category.items() if cur == currency]
        folded = fold_categories(items, ROW_LIMITS[data.kind], other)
        largest = max((amount for _, amount, _ in folded), default=0)
        rows = [{"name": clean_name(name, lang=lang), "amount": money(amount, currency),
                 "change": change_badge(amount, prev, lang),
                 "share": decimal_text(amount * 100 / expense, lang) + "%",
                 "bar": share_bar(amount, largest)} for name, amount, prev in folded]
        total_label = t("card_total", lang, _escape=False) if not mixed else t(
            "card_total_in", lang, _escape=False, currency=t(f"card_currency_{currency}", lang, _escape=False))
        result.append({
            "currency": currency, "title": t(f"card_section_{currency}", lang, _escape=False).upper(),
            "rows": rows, "total_label": total_label.upper(), "total": money(expense, currency),
            "prev_label": _prev_label(data, lang), "prev_total": money(previous, currency),
            "prev_change": change_badge(expense, previous, lang) if previous > 0 else None,
            "bars": _buckets(data, currency, lang),
        })
    return result


def _operations(data: CardData) -> List[dict]:
    """Expense operations of the window (rows of a split purchase summed), biggest first."""
    groups: Dict[str, dict] = {}
    for row in data.rows:
        op = groups.setdefault(row.group_id, {"amount": 0, "currency": row.currency, "category": row.category,
                                              "note": row.note, "when": row.occurred_at})
        op["amount"] += row.amount_minor
        op["note"] = op["note"] or row.note
    return sorted(groups.values(), key=lambda op: (-op["amount"], op["when"]))


def _op_name(op: dict, lang: str) -> str:
    return clean_name(op["note"] or op["category"], lang=lang)


def _budget_rows(data: CardData) -> List[db.BudgetUsage]:
    usable = [b for b in data.budgets if b.limit > 0]
    return sorted(usable, key=lambda b: (-b.spent * 10_000 // b.limit, b.category))


def _count(data: CardData) -> int:
    return len({row.group_id for row in data.rows})


def _dates(data: CardData) -> str:
    return f"{data.start.strftime('%d.%m.%Y')} — {data.last_day.strftime('%d.%m.%Y')}"


def _head(data: CardData, lang: str) -> dict:
    """Title, dates, meta line and stamp shared by all non-empty cards."""
    count = plural("expenses", _count(data), lang)
    spent = data.spent_currencies()
    if data.kind == "weekly":
        meta = f"{t('card_week_no', lang, _escape=False, week=data.start.isocalendar()[1])} · {count}"
    elif data.kind == "monthly":
        meta = f"{plural('days', (data.end - data.start).days, lang)} · {count}"
    elif len(spent) > 1:
        meta = f"{t('card_currencies', lang, _escape=False, n=len(spent))} · {count}"
    else:
        meta = f"{t('card_categories', lang, _escape=False)} · {count}"
    if len(spent) > 1:
        badge = {"main": "+".join(spent), "sub": t("card_separate", lang, _escape=False).upper(), "tone": "ink"}
    elif spent:
        badge = stamp(data.current.total("expense", spent[0]), data.previous.total("expense", spent[0]), lang)
    else:
        badge = None
    return {"title": t(f"card_title_{data.kind}", lang, _escape=False).upper(), "dates": _dates(data),
            "meta": meta, "stamp": badge}


def build_view(data: CardData, lang: str, username: str = "") -> dict:
    """The view-model of a card: what the template prints, every text already localized and formatted."""
    footer_right = t("card_thanks", lang, _escape=False)
    vm = {"lang": lang, "labels": _labels(lang), "footer_left": f"@{username}" if username else "",
          "footer_right": footer_right}
    if not data.spent_currencies():
        vm.update(template="empty", title=t(f"card_title_{data.kind}", lang, _escape=False).upper(),
                  dates=_dates(data), stamp=None, mixed=False,
                  meta=(f"{t('card_week_no', lang, _escape=False, week=data.start.isocalendar()[1])} · "
                        if data.kind == "weekly" else "") + plural("expenses", 0, lang),
                  empty={"stamp": t("card_empty_stamp", lang, _escape=False).upper(),
                         "when": t(f"card_empty_when_{data.kind}", lang, _escape=False).upper(),
                         "text": t(f"card_empty_text_{data.kind}", lang, _escape=False),
                         "hint": t("card_empty_hint", lang, _escape=False)})
        return vm

    sections = _sections(data, lang)
    vm.update(_head(data, lang), template=data.kind, sections=sections, mixed=len(sections) > 1)
    operations = _operations(data)
    budgets = _budget_rows(data)

    if data.kind == "weekly":
        vm["biggest"] = None
        if operations:
            op = operations[0]
            day = t("card_weekdays_long", lang, _escape=False).split()[op["when"].weekday()]
            vm["biggest"] = {"name": _op_name(op, lang), "suffix": f" · {day.upper()}",
                             "amount": money(op["amount"], op["currency"])}
        vm["budget_note"] = None
        if budgets:
            top = budgets[0]
            vm["budget_note"] = {"text": t("card_budget_note", lang, _escape=False, category=clean_name(
                top.category, upper=False, lang=lang), percent=top.percent), "over": top.spent > top.limit}

    elif data.kind == "monthly":
        vm["balances"] = []
        for currency in db.CURRENCIES:
            income, expense = data.current.total("income", currency), data.current.total("expense", currency)
            if not (income or expense):
                continue
            balance = income - expense
            prev = data.previous.total("income", currency) - data.previous.total("expense", currency)
            has_prev = bool(data.previous.total("income", currency) or data.previous.total("expense", currency))
            vm["balances"].append({
                "currency": currency, "income": money(income, currency, sign=True),
                "expense": money(-expense, currency), "balance": money(balance, currency, sign=True),
                "prev_balance": t("card_prev_balance", lang, _escape=False, amount=money(prev, currency, sign=True))
                if has_prev else "",
                "prev_change": _balance_change(balance, prev)})
        vm["top"] = [{"name": f"{i}. {_op_name(op, lang)}", "suffix": f" · {op['when'].strftime('%d.%m')}",
                      "amount": money(op["amount"], op["currency"])}
                     for i, op in enumerate(operations[:TOP_EXPENSES], 1)]
        vm["budgets"] = None
        if budgets:
            over = sum(1 for b in budgets if b.spent > b.limit)
            vm["budgets"] = {
                "over": t("card_budgets_over", lang, _escape=False, n=over) if over else "",
                "rows": [{"name": clean_name(b.category, lang=lang), "ascii": ascii_bar(b.spent, b.limit),
                          "percent": ("! " if b.spent > b.limit else "") + f"{b.percent}%",
                          "over": b.spent > b.limit} for b in budgets[:MAX_BUDGET_ROWS]]}
        vm["payments"] = [_payments(data, currency, lang) for currency in data.spent_currencies()]

    else:  # report
        if not vm["mixed"]:  # the two-currency receipt keeps the thank-you line, as in the mockup
            vm["footer_right"] = t("card_legend", lang, _escape=False)
        over = [b for b in budgets if b.spent > b.limit]
        vm["over_budget"] = None
        if over:
            vm["over_budget"] = {
                "count": t("card_over_count", lang, _escape=False, n=len(over)),
                "rows": [{"name": clean_name(b.category, lang=lang),
                          "amount": money(b.spent - b.limit, b.currency, sign=True), "percent": f"{b.percent}%"}
                         for b in over[:MAX_BUDGET_ROWS]]}
    return vm


def _balance_change(balance: int, previous: int) -> Optional[dict]:
    """Change of a positive previous balance; the receipt rule holds here too: ▲ (red) = more, ▼ (blue) = less."""
    if previous <= 0:
        return None
    percent = rep.change_percent(balance, previous)
    if percent > 0:
        return {"text": f"▲ {percent}%", "tone": "up"}
    if percent < 0:
        return {"text": f"▼ {-percent}%", "tone": "dn"}
    return None


def _payments(data: CardData, currency: str, lang: str) -> dict:
    """Spending of a currency split by the kind of account it was paid from, plus credit limit use."""
    sums = {kind: 0 for kind in PAY_KINDS}
    for row in data.rows:
        if row.currency == currency and row.account_kind in sums:
            sums[row.account_kind] += row.amount_minor
    total = sum(sums.values())
    parts = []
    for kind in PAY_KINDS:
        if sums[kind] > 0:
            share = sums[kind] * 100 / total
            parts.append({"kind": kind, "name": t(f"card_pay_{kind}", lang, _escape=False).upper(),
                          "amount": money(sums[kind], currency), "percent": f"{_half_up(Decimal(share))}%",
                          "width": f"{share:.2f}"})
    cards = [(debt, limit) for cur, debt, limit in data.credit if cur == currency and limit > 0]
    credit = None
    if cards:
        debt, limit = sum(c[0] for c in cards), sum(c[1] for c in cards)
        credit = {"used": f"{money(debt, currency)} / {money(limit, currency)}", "ascii": ascii_bar(debt, limit),
                  "percent": f"{debt * 100 // limit}%", "over": debt > limit}
    return {"currency": currency, "parts": parts, "credit": credit}


# ---- HTML ----

@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "j2"]),
                       undefined=StrictUndefined, trim_blocks=False, lstrip_blocks=False)


@lru_cache(maxsize=1)
def card_css() -> str:
    """The card stylesheet with JetBrains Mono embedded as data: URLs (works offline, no file:// access)."""
    faces = []
    for weight, name in FONT_FILES.items():
        data = base64.b64encode((FONTS / name).read_bytes()).decode("ascii")
        faces.append("@font-face{font-family:'JetBrains Mono';font-style:normal;font-weight:%d;font-display:block;"
                     "src:url(data:font/woff2;base64,%s) format('woff2')}" % (weight, data))
    return "\n".join(faces) + "\n" + (TEMPLATES / "card.css").read_text(encoding="utf-8")


def render_html(vm: dict) -> str:
    return _environment().get_template(f"{vm['template']}.html.j2").render(vm=vm, css=card_css())


# ---- Chromium ----

class RenderUnavailable(Exception):
    """Chromium / Playwright cannot be used right now."""


class CardRenderer:
    """One headless Chromium shared by every card: launched on first use, relaunched if it died, closed on
    shutdown. At most MAX_PAGES cards are rendered at a time."""

    def __init__(self, timeout: float = RENDER_TIMEOUT, pages: int = MAX_PAGES):
        self.timeout = timeout
        self._pages = pages
        self._playwright = None
        self._browser = None
        self._loop = None
        self._lock: Optional[asyncio.Lock] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._retry_at = 0.0  # monotonic time before which a failed launch is not retried

    def _sync_primitives(self) -> None:
        """Locks and the browser belong to one event loop (tests run a loop per test)."""
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self._lock = asyncio.Lock()
            self._semaphore = asyncio.Semaphore(self._pages)
            self._playwright = self._browser = None  # objects of a closed loop cannot be reused or closed

    async def _get_browser(self):
        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser
            if time.monotonic() < self._retry_at:
                raise RenderUnavailable("Chromium failed to start recently")
            await self._shutdown()
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(args=["--disable-gpu"])
            except Exception as err:  # noqa: BLE001 - missing package / browser, sandbox problems...
                self._retry_at = time.monotonic() + RETRY_LAUNCH_AFTER
                await self._shutdown()
                raise RenderUnavailable(f"cannot start Chromium: {err}") from err
            return self._browser

    async def _render(self, html: str) -> bytes:
        async with self._semaphore:
            browser = await self._get_browser()
            page = await browser.new_page(viewport={"width": WIDTH, "height": 800}, device_scale_factor=1)
            try:
                await page.set_content(html, wait_until="load")
                # every declared face, then whatever the layout still waits for
                await page.evaluate("Promise.all([...document.fonts].map(f => f.load()))"
                                    ".then(() => document.fonts.ready).then(() => document.fonts.size)")
                return await page.screenshot(full_page=True, type="png")
            finally:
                await page.close()

    async def render(self, html: str) -> bytes:
        """PNG of the page (full height). Raises RenderUnavailable, asyncio.TimeoutError or Playwright errors."""
        self._sync_primitives()
        return await asyncio.wait_for(self._render(html), self.timeout)

    async def _shutdown(self) -> None:
        browser, playwright = self._browser, self._playwright
        self._browser = self._playwright = None
        for closing in (browser.close if browser else None, playwright.stop if playwright else None):
            if closing is None:
                continue
            try:
                await closing()
            except Exception:  # noqa: BLE001 - already gone
                log.debug("Closing Chromium failed", exc_info=True)

    async def close(self) -> None:
        if self._loop is asyncio.get_running_loop():
            await self._shutdown()
        else:
            self._browser = self._playwright = None


renderer = CardRenderer()


async def close_renderer() -> None:
    await renderer.close()


async def render_card(data: CardData, lang: str) -> Optional[bytes]:
    """PNG of the card, or None if it could not be rendered (logged; the caller falls back)."""
    try:
        html = render_html(build_view(data, lang, _bot_username))
        return await renderer.render(html)
    except asyncio.TimeoutError:
        log.warning("Card rendering timed out after %ss", renderer.timeout)
    except RenderUnavailable as err:
        log.warning("Card rendering unavailable: %s", err)
    except Exception:  # noqa: BLE001 - a broken card must never break the report or the advice
        log.exception("Card rendering failed")
    return None


async def fallback_chart(data: CardData, lang: str) -> Optional[bytes]:
    """The matplotlib chart of the first spent currency, or None (text only) when it cannot be drawn either."""
    spent = data.spent_currencies()
    if not spent:
        return None
    currency = spent[0]
    items = [(name, amount) for (cur, name), amount in data.current.expense_by_category.items() if cur == currency]
    title = t("report_chart_title", lang, currency=currency, _escape=False)
    total = t("report_chart_total", lang, _escape=False,
              amount=f"{group(_half_up(Decimal(data.current.total('expense', currency)) / 100))} {currency}")
    try:
        from utils.charts import render_expense_chart
        from utils.misc.money import short_money

        return await asyncio.to_thread(render_expense_chart, items, title, total,
                                       t("report_chart_other", lang, _escape=False), short_money)
    except Exception:  # noqa: BLE001
        log.exception("Fallback chart failed")
        return None


async def card_or_chart(data: CardData, lang: str) -> Optional[bytes]:
    """The card; the matplotlib chart if the card fails; None if neither works."""
    png = await render_card(data, lang)
    return png if png is not None else await fallback_chart(data, lang)


# ---- Loading ----

async def load_card_data(user_id: int, kind: str, start: date, end: date, compare_start: date, compare_end: date,
                         budgets: Optional[List[db.BudgetUsage]] = None, through: Optional[date] = None,
                         partial: bool = False) -> CardData:
    """Read everything a card shows for the window [start, end) compared with [compare_start, compare_end)."""
    current = await db.range_summary(user_id, start, end)
    previous = await db.range_summary(user_id, compare_start, compare_end)
    rows = await db.expense_rows(user_id, start, end)
    if budgets is None:
        budgets = await db.budget_usages(user_id)
    credit = [(a.currency, db.debt(a), a.credit_limit_minor) for a in await db.list_accounts(user_id)
              if a.kind == "credit"]
    return CardData(kind, start, end, compare_start, compare_end, current, previous, rows, budgets, credit,
                    through=through, partial=partial)


async def report_data(user_id: int, report: db.PeriodReport) -> CardData:
    """Card data of a period report (the report screen and on-demand advice)."""
    partial = report.is_current and report.compare_end < report.start
    return await load_card_data(user_id, "report", report.start, report.end, report.compare_start,
                                report.compare_end, budgets=report.budgets, through=report.through,
                                partial=partial)


async def report_card(user_id: int, report: db.PeriodReport, lang: str) -> Optional[bytes]:
    """The report card PNG, or None if loading or rendering failed (the caller draws the old chart instead)."""
    try:
        data = await report_data(user_id, report)
    except Exception:  # noqa: BLE001
        log.exception("Could not load the report card data")
        return None
    return await render_card(data, lang)


async def advice_card(user_id: int, kind: str, lang: str, today: Optional[date] = None) -> Optional[bytes]:
    """Card for an advice of `kind` over the same window the advice reviewed: weekly / monthly receipt, or the
    running-period report for "now". Falls back to the matplotlib chart; None means text only."""
    from utils.ai.assistant import advice_windows

    try:
        today = today or db.now().date()
        if kind == "now":
            data = await report_data(user_id, await db.build_period_report(user_id, 0, today))
        else:
            user = await db.get_user(user_id)
            start, end, compare_start, compare_end = advice_windows(kind, today, user.salary_day)
            budgets = (await db.build_period_report(user_id, -1, today)).budgets if kind == "monthly" else None
            data = await load_card_data(user_id, kind, start, end, compare_start, compare_end, budgets=budgets)
    except Exception:  # noqa: BLE001
        log.exception("Could not load the %s card data", kind)
        return None
    return await card_or_chart(data, lang)
