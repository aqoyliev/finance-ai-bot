from loader import dp
from data.config import ADMIN_IDS
from .access import AccessMiddleware
from .language import LanguageMiddleware
from .throttling import ThrottlingMiddleware


if __name__ == "middlewares":
    # Order matters: drop strangers first, then resolve the language, then throttle
    dp.middleware.setup(AccessMiddleware(set(ADMIN_IDS)))
    dp.middleware.setup(LanguageMiddleware())
    dp.middleware.setup(ThrottlingMiddleware())
