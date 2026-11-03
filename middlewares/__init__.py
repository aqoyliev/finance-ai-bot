from loader import dp
from data.config import ADMINS
from .access import AccessMiddleware
from .language import LanguageMiddleware
from .throttling import ThrottlingMiddleware


if __name__ == "middlewares":
    # Order matters: drop strangers first, then resolve the language, then throttle
    dp.middleware.setup(AccessMiddleware({int(admin) for admin in ADMINS if str(admin).strip().isdigit()}))
    dp.middleware.setup(LanguageMiddleware())
    dp.middleware.setup(ThrottlingMiddleware())
