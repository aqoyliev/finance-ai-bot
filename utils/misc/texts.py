"""Formatting of domain objects into localized, HTML-safe text fragments."""
from typing import Iterable, List

from utils.db_api import finance as db
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
