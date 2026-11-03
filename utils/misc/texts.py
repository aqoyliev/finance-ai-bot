"""Formatting of domain objects into localized, HTML-safe text fragments."""
from html import escape
from typing import Iterable, List

from utils.db_api import finance as db
from utils.db_api import reports as rep
from utils.i18n import t

from .money import money_text


def balance_line(account, lang: str, with_limit: bool = True) -> str:
    if account.kind == "credit":
        key = "line_credit" if with_limit and account.credit_limit_minor else "line_credit_short"
        return t(key, lang, name=account.name,
                 debt=money_text(db.debt(account), account.currency),
                 limit=money_text(account.credit_limit_minor, account.currency),
                 available=money_text(db.available_credit(account), account.currency))
    return t("line_balance", lang, name=account.name, amount=money_text(account.balance_minor, account.currency))


def account_details(account, lang: str) -> str:
    lines = [t("account_title", lang, name=account.name),
             t("account_kind", lang, kind=t(f"kind_{account.kind}", lang), currency=account.currency)]
    if account.kind == "credit":
        lines.append(t("credit_debt", lang, amount=money_text(db.debt(account), account.currency)))
        if account.credit_limit_minor:
            lines.append(t("credit_limit", lang, amount=money_text(account.credit_limit_minor, account.currency)))
            lines.append(t("credit_available", lang,
                           amount=money_text(db.available_credit(account), account.currency)))
        else:
            lines.append(t("credit_no_limit", lang))
        lines.append(t("opening_debt", lang, amount=money_text(-account.opening_balance_minor, account.currency)))
    else:
        lines.append(t("account_balance", lang, amount=money_text(account.balance_minor, account.currency)))
        lines.append(t("opening_balance", lang,
                       amount=money_text(account.opening_balance_minor, account.currency)))
    return "\n".join(lines)


def over_limit_warning(accounts: Iterable, lang: str) -> List[str]:
    return [t("warn_over_limit", lang, name=a.name,
              debt=money_text(db.debt(a), a.currency),
              limit=money_text(a.credit_limit_minor, a.currency)) for a in accounts]


def operation_line(view, lang: str, escape: bool = True) -> str:
    """Short one-line description of an operation; escape=False for button labels (no HTML)."""
    tx = view.tx
    amount = money_text(tx.amount_minor, tx.currency)
    if view.is_transfer:
        key = "op_repayment" if view.counterpart_account.kind == "credit" else "op_transfer"
        return t(key, lang, amount=amount, source=view.account.name, target=view.counterpart_account.name,
                 date=tx.occurred_at.strftime("%d.%m"), _escape=escape)
    sign = "−" if tx.kind == "expense" else "+"
    category = tx.category or "—"
    if tx.subcategory:
        category = f"{category} / {tx.subcategory}"
    return t("op_line", lang, sign=sign, amount=amount, category=category, account=view.account.name,
             date=tx.occurred_at.strftime("%d.%m"), _escape=escape)


def operation_details(view, lang: str) -> str:
    tx = view.tx
    kind = t("kind_transfer_op", lang) if view.is_transfer else t(f"kind_{tx.kind}_op", lang)
    lines = [t("op_title", lang, kind=kind),
             t("op_amount", lang, amount=money_text(tx.amount_minor, tx.currency)),
             t("op_date", lang, date=tx.occurred_at.strftime("%d.%m.%Y %H:%M"))]
    if view.is_transfer:
        lines.append(t("op_from", lang, name=view.account.name))
        lines.append(t("op_to", lang, name=view.counterpart_account.name))
    else:
        lines.append(t("op_category", lang, category=tx.category or "—", subcategory=tx.subcategory or "—"))
        lines.append(t("op_account", lang, name=view.account.name))
    if tx.note:
        lines.append(t("op_note", lang, note=tx.note))
    return "\n".join(lines)


# ---- Reports, budgets, alerts ----

REPORT_MAX_CATEGORY_LINES = 10


def progress_bar(percent: int, width: int = 10) -> str:
    """Text progress bar; the bar is full from 100% on."""
    filled = max(0, min(width, round(percent * width / 100)))
    return "▓" * filled + "░" * (width - filled)


def change_text(current: int, previous: int, lang: str) -> str:
    """'▲ 12%' / '▼ 5%' / '= 0%' versus the previous period, 'new' if there was nothing before; '' if both 0."""
    pct = rep.change_percent(current, previous)
    if pct is None:
        return t("report_new", lang) if current > 0 else ""
    return f"▲ {pct}%" if pct > 0 else f"▼ {-pct}%" if pct < 0 else "= 0%"


def _totals_block(currency: str, income: int, expense: int, prev_expense: int, lang: str) -> str:
    change = change_text(expense, prev_expense, lang) if prev_expense else ""
    return t("report_totals", lang, income=money_text(income, currency), expense=money_text(expense, currency),
             change=f" ({change})" if change else "", balance=money_text(income - expense, currency))


def category_lines(summary, lang: str) -> List[str]:
    lines = []
    for number, row in enumerate(summary.categories[:REPORT_MAX_CATEGORY_LINES], 1):
        change = change_text(row.amount, row.prev_amount, lang)
        lines.append(f"{number}. {escape(row.name)} — {money_text(row.amount, summary.currency)} · {row.share}%"
                     + (f" · {change}" if change else ""))
    rest = summary.categories[REPORT_MAX_CATEGORY_LINES:]
    if rest:
        total = sum(row.amount for row in rest)
        lines.append(f"… {t('report_chart_other', lang)} ({len(rest)}) — {money_text(total, summary.currency)} · "
                     f"{rep.share_percent(total, summary.expense)}%")
    return lines


def budget_usage_line(usage, lang: str) -> str:
    return t("report_budget_line", lang, category=usage.category, spent=money_text(usage.spent, usage.currency),
             limit=money_text(usage.limit, usage.currency), percent=str(usage.percent),
             bar=progress_bar(usage.percent))


def report_title(report, lang: str) -> str:
    fmt = "%d.%m.%Y"
    if report.is_current:
        return t("report_title_current", lang, start=report.start.strftime(fmt))
    return t("report_title_past", lang, start=report.start.strftime(fmt), end=report.last_day.strftime(fmt))


def report_text(report, lang: str) -> str:
    """The full text summary of a PeriodReport (income, expenses, categories, budgets)."""
    lines = [report_title(report, lang), ""]
    if not report.has_data:
        lines.append(t("report_empty", lang))
    for summary in report.currencies:
        lines += [f"<b>{summary.currency}</b>",
                  _totals_block(summary.currency, summary.income, summary.expense, summary.prev_expense, lang)]
        if summary.categories:
            lines += ["", t("report_by_category", lang)] + category_lines(summary, lang)
        lines.append("")
    if report.combined:
        c = report.combined
        lines += [t("report_combined_head", lang, rate=f"{report.usd_rate:f}"),
                  _totals_block("UZS", c.income, c.expense, c.prev_expense, lang), ""]
    elif len(report.currencies) > 1:
        lines += [t("rate_hint", lang), ""]
    if report.budgets:
        lines.append(t("report_budgets_head", lang))
        lines += [budget_usage_line(usage, lang) for usage in report.budgets]
        lines.append("")
    if report.has_data and any(s.prev_expense for s in report.currencies):
        key = "report_compare_same_days" if report.is_current else "report_compare_full"
        fmt = "%d.%m"
        lines.append(t(key, lang, start=report.compare_start.strftime(fmt), end=report.compare_last_day.strftime(fmt)))
    return "\n".join(lines).strip()


def subcategory_text(report, category: str, by_currency, lang: str) -> str:
    fmt = "%d.%m.%Y"
    lines = [t("report_sub_title", lang, category=category, start=report.start.strftime(fmt),
               end=report.through.strftime(fmt)), ""]
    if not by_currency:
        lines.append(t("report_sub_empty", lang))
    for currency in db.CURRENCIES:
        items = by_currency.get(currency)
        if not items:
            continue
        total = sum(amount for _, amount in items)
        lines.append(f"<b>{currency}</b> — {money_text(total, currency)}")
        for number, (name, amount) in enumerate(items, 1):
            label = t("report_no_sub", lang) if name == rep.NO_CATEGORY else escape(name)
            lines.append(f"{number}. {label} — {money_text(amount, currency)} · "
                         f"{rep.share_percent(amount, total)}%")
        lines.append("")
    return "\n".join(lines).strip()


def alert_text(alert, lang: str) -> str:
    return t(f"alert_{alert.kind}_{alert.threshold}", lang, name=alert.name,
             used=money_text(alert.used, alert.currency), limit=money_text(alert.limit, alert.currency),
             percent=str(alert.percent), bar=progress_bar(alert.percent))
