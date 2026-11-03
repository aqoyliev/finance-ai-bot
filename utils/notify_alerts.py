"""Sends limit alerts (category budgets, credit card limits) after operations were saved or edited.

Every handler that saves or edits an operation calls `send_alerts` once, passing what it saved; the
decision what to say lives in `db.check_alerts`.
"""
import logging

from loader import bot
from utils.db_api import finance as db
from utils.misc.texts import alert_text

log = logging.getLogger(__name__)


async def send_alerts(user_id: int, lang: str, *saved: db.SavedOperation) -> None:
    """Check the budgets of the saved expenses' categories and the credit cards they touched.

    Never raises: a failed alert must not break saving. The save confirmation already warns about a credit
    card above its limit, so that case is passed on as `already_warned` and not repeated.
    """
    categories = [tx.category for op in saved for tx in op.transactions if tx.kind == "expense" and tx.category]
    accounts = [a for op in saved for a in op.accounts]
    try:
        over_limit = [a.id for a in accounts if db.is_over_limit(a)]
        alerts = await db.check_alerts(user_id, categories, [a.id for a in accounts], already_warned=over_limit)
        for alert in alerts:
            await bot.send_message(user_id, alert_text(alert, lang))
    except Exception:  # noqa: BLE001
        log.exception("Could not send limit alerts")
