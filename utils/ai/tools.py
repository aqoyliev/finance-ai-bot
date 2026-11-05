"""Client-side tools of the Ask AI assistant: strict JSON-schema definitions plus their executor.

Every tool is read-only and backed by the service layer (utils/db_api), so the model fetches only the data a
question needs instead of receiving the whole database. Results are compact JSON with human amounts (major
units, e.g. 125000.5) and an explicit currency. Transfers between own accounts are never income or expense.
"""
import json
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from utils.db_api import finance as db
from utils.db_api import reports as rep
from utils.misc.money import MAX_AMOUNT

log = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50
MAX_PAST_PERIODS = 120  # how far back period_offset may go


class ToolError(Exception):
    """Bad tool input; the message is returned to the model as an is_error tool_result."""


# ---- Definitions ----

def _nullable(schema: dict, description: str) -> dict:
    return {"anyOf": [schema, {"type": "null"}], "description": description}


def _tool(name: str, description: str, properties: Optional[dict] = None) -> dict:
    properties = properties or {}
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {"type": "object", "properties": properties, "required": list(properties),
                         "additionalProperties": False},
    }


_OFFSET = {"type": "integer", "description": "Financial period: 0 = current (it began on the user's salary day), "
                                             "-1 = previous, -2 = the one before, and so on. Never positive."}

TOOLS: List[dict] = [
    _tool("get_period_summary",
          "Income, expenses and balance per currency for one financial period (from salary day to salary day), "
          "expenses by category with share and change versus the comparison window (the same number of days of "
          "the previous period while a period is running, the whole previous period otherwise), a combined UZS "
          "total when a USD rate is known, and budget usage in that period. Start here for questions about a "
          "month or a period.",
          {"period_offset": _OFFSET}),
    _tool("get_category_breakdown",
          "Expenses of one expense category in a financial period, split by subcategory, with the category "
          "total of the comparison window. Use the exact category name from get_categories or a summary.",
          {"category": {"type": "string", "description": "Expense category name"}, "period_offset": _OFFSET}),
    _tool("search_transactions",
          "Find individual operations. All filters are optional (null = no filter) and combined with AND. "
          "Returns the matching count, the totals of all matches per kind and currency, and the newest "
          "matches (up to `limit`). Use it for specific dates, merchants/notes, accounts, amounts or "
          "subcategories, and for windows that are not a whole financial period.",
          {
              "date_from": _nullable({"type": "string"}, "First day, inclusive, 'YYYY-MM-DD'"),
              "date_to": _nullable({"type": "string"}, "Last day, inclusive, 'YYYY-MM-DD'"),
              "kind": _nullable({"type": "string", "enum": ["expense", "income", "transfer"]}, "Operation kind"),
              "category": _nullable({"type": "string"}, "Category or subcategory name (exact, case-insensitive)"),
              "account": _nullable({"type": "string"}, "Account name or part of it"),
              "text": _nullable({"type": "string"}, "Words to look for in the note, category or subcategory"),
              "min_amount": _nullable({"type": "number"}, "Minimum amount in the operation's own currency"),
              "max_amount": _nullable({"type": "number"}, "Maximum amount in the operation's own currency"),
              "limit": _nullable({"type": "integer"}, f"How many operations to list (default "
                                                      f"{DEFAULT_SEARCH_LIMIT}, at most {MAX_SEARCH_LIMIT})"),
          }),
    _tool("get_accounts",
          "Active accounts with their current balance; credit cards also show debt, limit, available credit "
          "and the share of the limit used."),
    _tool("get_budgets",
          "Monthly category budgets (limits) of the current financial period with spent amount, percent used "
          "and what is left. Spending in the other currency is converted at the USD rate in use (get_exchange_rate)."),
    _tool("get_categories", "The user's expense categories with their subcategories, and income categories."),
    _tool("get_exchange_rate",
          "The USD -> UZS rate in use with its source and date: the official Central Bank of Uzbekistan rate (or, if "
          "that is unreachable, an international market rate, marked as such), or the user's own override set in the Mini App settings (used for combined totals). usd_to_uzs is null if no rate is "
          "known. This is the only source for exchange rates; never quote one from memory."),
]

TOOL_NAMES = tuple(tool["name"] for tool in TOOLS)


# ---- Formatting helpers ----

def amount(minor: int):
    """Minor units -> a JSON number in major units (whole numbers stay integers)."""
    value = Decimal(minor) / 100
    return int(value) if value == value.to_integral_value() else float(value)


def _day(value: date) -> str:
    return value.isoformat()


def _period(report: db.PeriodReport) -> dict:
    return {"start": _day(report.start), "last_day": _day(report.last_day), "is_current": report.is_current,
            "data_through": _day(report.through)}


def _clean(data: dict) -> dict:
    """Drop None values to keep the result short."""
    return {key: value for key, value in data.items() if value is not None}


def _offset(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError("period_offset must be an integer (0 = current, -1 = previous)")
    if value > 0:
        raise ToolError("period_offset cannot be positive: future periods have no data")
    if value < -MAX_PAST_PERIODS:
        raise ToolError(f"period_offset must be >= -{MAX_PAST_PERIODS}")
    return value


def _date(value: Any, name: str) -> Optional[date]:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ToolError(f"{name} must be a date 'YYYY-MM-DD'")


def _minor(value: Any, name: str) -> Optional[int]:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ToolError(f"{name} must be a number")
    if not number.is_finite() or number < 0 or number > MAX_AMOUNT:
        raise ToolError(f"{name} is out of range")
    return int(number * 100)


def _fold(text: Any) -> str:
    return " ".join(str(text or "").casefold().replace("ʻ", "'").replace("’", "'").split())


def budget_json(usage: db.BudgetUsage) -> dict:
    return {"category": usage.category, "currency": usage.currency, "limit": amount(usage.limit),
            "spent": amount(usage.spent), "used_pct": usage.percent,
            "left": amount(max(usage.limit - usage.spent, 0))}


# ---- Tools ----

async def get_period_summary(user_id: int, period_offset: int) -> dict:
    report = await db.build_period_report(user_id, _offset(period_offset))
    currencies = []
    for summary in report.currencies:
        currencies.append(_clean({
            "currency": summary.currency, "income": amount(summary.income), "expense": amount(summary.expense),
            "balance": amount(summary.balance), "comparison_expense": amount(summary.prev_expense),
            "expense_change_pct": summary.expense_change,
            "expenses_by_category": [_clean({
                "category": row.name, "amount": amount(row.amount), "share_pct": row.share,
                "comparison_amount": amount(row.prev_amount), "change_pct": row.change})
                for row in summary.categories],
        }))
    same_days = report.is_current and report.compare_end < report.start
    result = {
        "period": _period(report),
        "comparison_window": {"start": _day(report.compare_start), "last_day": _day(report.compare_last_day),
                              "kind": "same days of the previous period" if same_days else "whole previous period"},
        "currencies": currencies or "no income or expenses in this period",
        "earlier_data_exists": report.has_earlier,
    }
    if report.combined:
        combined = report.combined
        info = rate_json(await db.get_usd_rate_info(user_id))
        result["combined_in_uzs"] = _clean({
            "usd_rate": str(combined.rate), "usd_rate_source": info["source"], "usd_rate_date": info["date"], "income": amount(combined.income), "expense": amount(combined.expense),
            "balance": amount(combined.balance), "comparison_expense": amount(combined.prev_expense),
            "expense_change_pct": combined.expense_change})
    if report.budgets:
        result["budgets"] = [budget_json(usage) for usage in report.budgets]
    return result


async def get_category_breakdown(user_id: int, category: str, period_offset: int) -> dict:
    names = [c.name for c in await db.list_categories(user_id, "expense")]
    wanted = _fold(category)
    name = next((n for n in names if _fold(n) == wanted), None)
    if name is None:
        raise ToolError(f"Unknown expense category {category!r}. Categories: {', '.join(names)}")
    report = await db.build_period_report(user_id, _offset(period_offset))
    by_currency = await db.expense_by_subcategory(user_id, name, report.start, report.end)
    currencies = []
    for currency, items in by_currency.items():
        total = sum(value for _, value in items)
        previous = next((row.prev_amount for s in report.currencies if s.currency == currency
                         for row in s.categories if row.name == name), 0)
        currencies.append(_clean({
            "currency": currency, "total": amount(total), "comparison_total": amount(previous),
            "change_pct": rep.change_percent(total, previous),
            "subcategories": [{"subcategory": sub if sub != rep.NO_CATEGORY else None, "amount": amount(value),
                               "share_pct": rep.share_percent(value, total)} for sub, value in items],
        }))
    return {"category": name, "period": _period(report),
            "comparison_window": {"start": _day(report.compare_start), "last_day": _day(report.compare_last_day)},
            "currencies": currencies or "no expenses in this category in this period"}


async def search_transactions(user_id: int, date_from=None, date_to=None, kind=None, category=None,
                              account=None, text=None, min_amount=None, max_amount=None, limit=None) -> dict:
    start, end = _date(date_from, "date_from"), _date(date_to, "date_to")
    if start and end and start > end:
        raise ToolError("date_from is after date_to")
    if kind not in (None, "expense", "income", "transfer"):
        raise ToolError("kind must be expense, income, transfer or null")
    account_ids = None
    if account:
        accounts = await db.list_accounts(user_id)
        wanted = _fold(account)
        account_ids = [a.id for a in accounts if wanted in _fold(a.name)]
        if not account_ids:
            raise ToolError(f"No account matches {account!r}. Accounts: {', '.join(a.name for a in accounts)}")
    if limit is None:
        limit = DEFAULT_SEARCH_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ToolError("limit must be a non-negative integer")
    found = await db.search_transactions(
        user_id, start, end, kind, category or None, account_ids, text or None,
        _minor(min_amount, "min_amount"), _minor(max_amount, "max_amount"), min(limit, MAX_SEARCH_LIMIT))
    return {
        "count": found.count,
        "totals": [{"kind": kind_, "currency": currency, "amount": amount(value)}
                   for (kind_, currency), value in sorted(found.totals.items())],
        "transactions": [_clean({
            "date": row.occurred_at.strftime("%Y-%m-%d %H:%M"), "kind": row.kind, "amount": amount(row.amount_minor),
            "currency": row.currency, "category": row.category, "subcategory": row.subcategory,
            "account": row.account, "to_account": row.to_account, "note": row.note}) for row in found.rows],
        "listed": len(found.rows),
    }


async def get_accounts(user_id: int) -> dict:
    result = []
    for account in await db.list_accounts(user_id):
        item = {"name": account.name, "kind": account.kind, "currency": account.currency,
                "balance": amount(account.balance_minor)}
        if account.kind == "credit":
            item["debt"] = amount(db.debt(account))
            if account.credit_limit_minor:
                item["credit_limit"] = amount(account.credit_limit_minor)
                item["available_credit"] = amount(db.available_credit(account))
                item["limit_used_pct"] = db.debt(account) * 100 // account.credit_limit_minor
        result.append(item)
    return {"accounts": result}


async def get_budgets(user_id: int) -> dict:
    user = await db.get_user(user_id)
    start, end = db.period_bounds(user.salary_day, db.now().date())
    usages = await db.budget_usages(user_id)
    return {"period": {"start": _day(start), "last_day": _day(end - timedelta(days=1))},
            "budgets": [budget_json(u) for u in usages] or "no budgets set"}


async def get_categories(user_id: int) -> dict:
    expense = {}
    for category in await db.list_categories(user_id, "expense"):
        expense[category.name] = [s.name for s in await db.list_subcategories(category.id)]
    income = [c.name for c in await db.list_categories(user_id, "income")]
    return {"expense": expense, "income": income}


def rate_json(info: Optional[db.UsdRate]) -> dict:
    """The rate in use with its source and date, for tool results and prompts (None: no rate is known)."""
    if info is None:
        return {"usd_to_uzs": None, "source": None, "date": None}
    source = {"cbu": "Central Bank of Uzbekistan official rate",
              "market": "international market rate (not the Central Bank)"}.get(info.source, "set manually by the user")
    return {"usd_to_uzs": str(info.rate), "source": source,
            "date": info.day.isoformat() if info.day else None}


async def get_exchange_rate(user_id: int) -> dict:
    return rate_json(await db.get_usd_rate_info(user_id))


_HANDLERS = {
    "get_period_summary": get_period_summary,
    "get_category_breakdown": get_category_breakdown,
    "search_transactions": search_transactions,
    "get_accounts": get_accounts,
    "get_budgets": get_budgets,
    "get_categories": get_categories,
    "get_exchange_rate": get_exchange_rate,
}


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


async def run_tool(user_id: int, name: str, arguments: Any) -> Tuple[str, bool]:
    """Execute one tool call for the user. Returns (JSON text, is_error); never raises."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return dumps({"error": f"Unknown tool {name!r}"}), True
    if not isinstance(arguments, dict):
        return dumps({"error": "Tool input must be an object"}), True
    try:
        return dumps(await handler(user_id, **arguments)), False
    except ToolError as err:
        return dumps({"error": str(err)}), True
    except TypeError as err:  # unexpected / missing arguments
        return dumps({"error": f"Bad arguments: {err}"}), True
    except Exception:  # noqa: BLE001 - a broken tool must not break the answer
        log.exception("Tool %s failed", name)
        return dumps({"error": "Internal error while reading the data"}), True
