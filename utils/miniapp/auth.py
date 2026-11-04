"""Validation of Telegram Mini App initData (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).

The Mini App sends Telegram.WebApp.initData with every API call. It is a query string signed by Telegram:
hash = HMAC_SHA256(data_check_string, key=HMAC_SHA256(BOT_TOKEN, key="WebAppData")), where data_check_string
is every other field as "key=value", sorted by key and joined with "\n". Never log initData or the token.
"""
import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qsl

MAX_AGE = 24 * 60 * 60  # initData older than a day is refused
MAX_CLOCK_SKEW = 5 * 60  # auth_date slightly in the future (clock drift) is still fine
MAX_LENGTH = 8192


class InitDataError(Exception):
    """initData is missing, malformed, wrongly signed or expired."""


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign(fields: dict, bot_token: str) -> str:
    """The hash Telegram would put next to these fields (used by tests and local QA)."""
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    return hmac.new(_secret_key(bot_token), check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(init_data: Optional[str], bot_token: str, max_age: int = MAX_AGE,
                       now: Optional[float] = None) -> dict:
    """Checked initData fields, with "user" decoded from JSON. Raises InitDataError."""
    if not init_data or len(init_data) > MAX_LENGTH:
        raise InitDataError("missing")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InitDataError("malformed") from None
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise InitDataError("duplicate field")
    received = fields.pop("hash", "")
    if not received or not hmac.compare_digest(sign(fields, bot_token), received.lower()):
        raise InitDataError("bad signature")

    try:
        auth_date = int(fields.get("auth_date", ""))
    except ValueError:
        raise InitDataError("no auth_date") from None
    age = (time.time() if now is None else now) - auth_date
    if age > max_age or age < -MAX_CLOCK_SKEW:
        raise InitDataError("expired")

    try:
        user = json.loads(fields.get("user", ""))
        user_id = user["id"]
    except (ValueError, TypeError, KeyError):
        raise InitDataError("no user") from None
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise InitDataError("no user")
    fields["user"] = user
    fields["user_id"] = user_id
    return fields
