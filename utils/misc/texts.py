"""Formatting of domain objects into localized, HTML-safe text fragments."""
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Iterable, List

from utils.db_api import finance as db
from utils.i18n import TEXTS, t

from .money import money_text


def over_limit_warning(accounts: Iterable, lang: str) -> List[str]:
    return [t("warn_over_limit", lang, name=a.name,
              debt=money_text(db.debt(a), a.currency),
              limit=money_text(a.credit_limit_minor, a.currency)) for a in accounts]


# ---- Saved operation card ----

CARD_SEPARATOR = "──────────────"


def card_amount(minor: int, currency: str, lang: str) -> str:
    """'25 000 so'm' / '12.50 USD': no zero cents, the currency as on the report cards."""
    amount = Decimal(minor) / Decimal(100)
    number = f"{amount:,.0f}" if amount == amount.to_integral_value() else f"{amount:,.2f}"
    unit = t(f"card_currency_{currency}", lang) if f"card_currency_{currency}" in TEXTS else currency
    return f"{number.replace(',', ' ')} {unit}"


def card_time(moment: datetime, lang: str) -> str:
    """'04 Noy, 22:15'."""
    month = t("months_short", lang).split()[moment.month - 1]
    return f"{moment.day:02d} {month}, {moment:%H:%M}"


def operation_card(saved, lang: str) -> str:
    """Short HTML card of a just saved operation (expense, income or transfer; a SavedOperation).

    Header with an emoji, separator lines, amount, category, account(s), time, and the note when there is one."""
    rows = saved.transactions
    first = rows[0]
    names = {a.id: a.name for a in saved.accounts}
    lines = [t(f"opcard_{first.kind}", lang), CARD_SEPARATOR]
    if first.kind == "transfer":
        out = next((r for r in rows if r.direction == "out"), first)
        incoming = next((r for r in rows if r.direction == "in"), None)
        lines += [t("opcard_amount", lang, amount=card_amount(out.amount_minor, out.currency, lang)),
                  t("opcard_from", lang, name=names.get(out.account_id, "—")),
                  t("opcard_to", lang, name=names.get(incoming.account_id, "—") if incoming else "—")]
    else:
        category = first.category or "—"
        if first.subcategory:
            category = f"{category} › {first.subcategory}"
        accounts = ", ".join(dict.fromkeys(names.get(r.account_id, "—") for r in rows))
        lines += [t("opcard_amount", lang, amount=card_amount(sum(r.amount_minor for r in rows), first.currency, lang)),
                  t("opcard_category", lang, category=category),
                  t("opcard_payment" if first.kind == "expense" else "opcard_account", lang, name=accounts)]
    lines += [t("opcard_time", lang, time=card_time(first.occurred_at, lang)), CARD_SEPARATOR]
    if first.note:
        lines.append(f"📝 {escape(first.note)}")
    return "\n".join(lines)



def progress_bar(percent: int, width: int = 10) -> str:
    """Text progress bar; the bar is full from 100% on."""
    filled = max(0, min(width, round(percent * width / 100)))
    return "▓" * filled + "░" * (width - filled)


def alert_text(alert, lang: str) -> str:
    return t(f"alert_{alert.kind}_{alert.threshold}", lang, name=alert.name,
             used=money_text(alert.used, alert.currency), limit=money_text(alert.limit, alert.currency),
             percent=str(alert.percent), bar=progress_bar(alert.percent))


def split_message(text: str, limit: int = 4000) -> List[str]:
    """Split a long (already escaped) text into Telegram-sized parts, preferring line breaks."""
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        # never cut inside an HTML entity such as &amp;
        amp = text.rfind("&", 0, cut)
        if amp != -1 and ";" not in text[amp:cut]:
            cut = amp
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n ")
    parts.append(text)
    return [part for part in parts if part] or [""]
