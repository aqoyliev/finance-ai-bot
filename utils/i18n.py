"""Translation layer: every user-facing text lives here, in Uzbek (Latin), Russian and English.

Usage: t("key", lang, **kwargs). String kwargs are HTML-escaped (messages use parse_mode=HTML);
pass _escape=False for plain-text targets such as button labels or callback alerts.
"""
from html import escape
from typing import Optional

LANGUAGES = ("uz", "ru", "en")
DEFAULT_LANGUAGE = "uz"
LANGUAGE_NAMES = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}


def guess_language(code: Optional[str]) -> str:
    """Map a Telegram language_code (e.g. 'ru-RU') to a supported language."""
    code = (code or "").split("-")[0].lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def t(key: str, lang: Optional[str] = None, *, _escape: bool = True, **kwargs) -> str:
    variants = TEXTS[key]
    text = variants.get(lang or DEFAULT_LANGUAGE) or variants["en"]
    if not kwargs:
        return text
    if _escape:
        kwargs = {k: escape(v, quote=False) if isinstance(v, str) else v for k, v in kwargs.items()}
    return text.format(**kwargs)


CHOOSE_LANGUAGE = "Tilni tanlang / Выберите язык / Choose a language:"

TEXTS = {
    # ---- General ----
    "choose_language": {"uz": CHOOSE_LANGUAGE, "ru": CHOOSE_LANGUAGE, "en": CHOOSE_LANGUAGE},
    "private_bot": {
        "uz": "Bu shaxsiy bot. Kirish yopiq.",
        "ru": "Это личный бот. Доступ закрыт.",
        "en": "This is a private bot. Access is restricted.",
    },
    "too_many_requests": {
        "uz": "Juda ko'p so'rov! Biroz kuting.",
        "ru": "Слишком много запросов! Подождите немного.",
        "en": "Too many requests! Please wait a moment.",
    },
    "start": {
        "uz": "<b>MOLIYA BOTI</b>\n\nAmalni tanlang.\nMaosh kunini belgilash: /salaryday 5\n"
              "Dollar kursini belgilash: /rate 1 USD 12700 UZS",
        "ru": "<b>ФИНАНСОВЫЙ БОТ</b>\n\nВыберите действие.\nДень зарплаты: /salaryday 5\n"
              "Курс доллара: /rate 1 USD 12700 UZS",
        "en": "<b>FINANCE BOT</b>\n\nChoose an action.\nSet your salary day: /salaryday 5\n"
              "Set the USD rate: /rate 1 USD 12700 UZS",
    },
    "bot_started": {"uz": "Bot ishga tushdi", "ru": "Бот запущен", "en": "Bot has started"},
    "cmd_start": {"uz": "Asosiy menyu", "ru": "Главное меню", "en": "Open the main menu"},
    "cmd_salaryday": {"uz": "Maosh kuni, masalan /salaryday 5", "ru": "День зарплаты, например /salaryday 5",
                      "en": "Set salary day, e.g. /salaryday 5"},
    "cmd_rate": {"uz": "Dollar kursi, masalan /rate 1 USD 12700 UZS",
                 "ru": "Курс доллара, например /rate 1 USD 12700 UZS",
                 "en": "Set USD rate, e.g. /rate 1 USD 12700 UZS"},
    "cmd_help": {"uz": "Yordam", "ru": "Помощь", "en": "Help"},
    "main_menu": {"uz": "Asosiy menyu:", "ru": "Главное меню:", "en": "Main menu:"},
    "language_changed": {
        "uz": "Til o'zgartirildi: o'zbekcha.",
        "ru": "Язык изменён: русский.",
        "en": "Language changed: English.",
    },
    "help": {
        "uz": "<b>Buyruqlar</b>\n"
              "/start — asosiy menyu\n"
              "/salaryday 5 — moliyaviy oy boshlanadigan kun (1–28)\n"
              "/rate 1 USD 12700 UZS — dollar kursi\n"
              "/help — yordam\n\n"
              "<b>Menyu</b>\n"
              "➖ Xarajat / ➕ Daromad — amalni yozish (xaridni bir nechta hisobdan to'lash mumkin)\n"
              "🔁 O'tkazma — o'z hisoblaringiz orasida pul o'tkazish, kredit kartani so'ndirish\n"
              "💳 Hisoblar — hisoblar, kredit limiti va qarz; qo'shish, tahrirlash, o'chirish\n"
              "📊 Hisobot — moliyaviy oy uchun daromad va xarajatlar (o'tkazmalar hisobga olinmaydi)\n"
              "🧾 Tarix — so'nggi amallar; amalni ochib tahrirlash yoki o'chirish mumkin\n"
              "⚙️ Sozlamalar — hisoblar va til\n\n"
              "<b>🤖 AI kiritish</b>\n"
              "Menyusiz yozish: chek rasmini, ovozli xabarni, bank SMS'ini yoki oddiy matnni yuboring "
              "(masalan «taksi 25000 uob kartadan», «kofe 18 ming naqd»). Bot qoralama ko'rsatadi — "
              "tekshiring, kerak bo'lsa tahrirlang va ✅ Saqlash ni bosing. "
              "Rasm va ovoz tahlil uchun Google Gemini'ga yuboriladi.",
        "ru": "<b>Команды</b>\n"
              "/start — главное меню\n"
              "/salaryday 5 — день начала финансового месяца (1–28)\n"
              "/rate 1 USD 12700 UZS — курс доллара\n"
              "/help — помощь\n\n"
              "<b>Меню</b>\n"
              "➖ Расход / ➕ Доход — записать операцию (покупку можно оплатить с нескольких счетов)\n"
              "🔁 Перевод — перевод между своими счетами, погашение кредитной карты\n"
              "💳 Счета — счета, кредитный лимит и долг; добавить, изменить, отключить\n"
              "📊 Отчёт — доходы и расходы за финансовый месяц (переводы не учитываются)\n"
              "🧾 История — последние операции; откройте операцию, чтобы изменить или удалить её\n"
              "⚙️ Настройки — счета и язык\n\n"
              "<b>🤖 AI-ввод</b>\n"
              "Без меню: отправьте фото чека, голосовое, банковское SMS или просто текст "
              "(например «такси 25000 uob», «кофе 18 тысяч наличными»). Бот покажет черновик — проверьте, "
              "при необходимости измените и нажмите ✅ Сохранить. "
              "Фото и голос отправляются на анализ в Google Gemini.",
        "en": "<b>Commands</b>\n"
              "/start — main menu\n"
              "/salaryday 5 — day your financial month starts (1–28)\n"
              "/rate 1 USD 12700 UZS — USD exchange rate\n"
              "/help — help\n\n"
              "<b>Menu</b>\n"
              "➖ Expense / ➕ Income — record an operation (a purchase can be paid from several accounts)\n"
              "🔁 Transfer — move money between your own accounts, repay a credit card\n"
              "💳 Accounts — accounts, credit limit and debt; add, edit, deactivate\n"
              "📊 Report — income and expenses for the financial month (transfers are not counted)\n"
              "🧾 History — recent operations; open one to edit or delete it\n"
              "⚙️ Settings — accounts and language\n\n"
              "<b>🤖 AI input</b>\n"
              "Skip the menus: send a receipt photo, a voice message, a bank SMS or plain text "
              "(e.g. \"taxi 25000 from uob\", \"got salary 12m to hamkorbank\"). The bot shows a draft — "
              "check it, edit if needed and press ✅ Save. "
              "Photos and voice are sent to Google Gemini for analysis.",
    },
    "use_menu": {
        "uz": "Quyidagi menyudan foydalaning.",
        "ru": "Воспользуйтесь меню ниже.",
        "en": "Please use the menu below.",
    },
    "session_lost": {
        "uz": "Sessiya tugadi. Qaytadan boshlang: /start",
        "ru": "Сессия истекла. Начните заново: /start",
        "en": "Session expired. Start again: /start",
    },
    "cancelled": {"uz": "Bekor qilindi.", "ru": "Отменено.", "en": "Cancelled."},

    # ---- Buttons ----
    "btn_expense": {"uz": "➖ XARAJAT", "ru": "➖ РАСХОД", "en": "➖ EXPENSE"},
    "btn_income": {"uz": "➕ DAROMAD", "ru": "➕ ДОХОД", "en": "➕ INCOME"},
    "btn_transfer": {"uz": "🔁 O'TKAZMA", "ru": "🔁 ПЕРЕВОД", "en": "🔁 TRANSFER"},
    "btn_accounts": {"uz": "💳 HISOBLAR", "ru": "💳 СЧЕТА", "en": "💳 ACCOUNTS"},
    "btn_report": {"uz": "📊 HISOBOT", "ru": "📊 ОТЧЁТ", "en": "📊 REPORT"},
    "btn_history": {"uz": "🧾 TARIX", "ru": "🧾 ИСТОРИЯ", "en": "🧾 HISTORY"},
    "btn_settings": {"uz": "⚙️ SOZLAMALAR", "ru": "⚙️ НАСТРОЙКИ", "en": "⚙️ SETTINGS"},
    "btn_cancel": {"uz": "Bekor qilish", "ru": "Отмена", "en": "Cancel"},
    "btn_back": {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад", "en": "⬅️ Back"},
    "btn_language": {"uz": "🌐 Til", "ru": "🌐 Язык", "en": "🌐 Language"},
    "btn_no_subcategory": {"uz": "Subkategoriyasiz", "ru": "Без подкатегории", "en": "No subcategory"},
    "btn_split_more": {
        "uz": "Ha, yana bir qism qo'shish", "ru": "Да, добавить ещё часть", "en": "Yes, add another part",
    },
    "btn_split_finish": {"uz": "Yo'q, yakunlash", "ru": "Нет, завершить", "en": "No, finish"},
    "btn_add_account": {"uz": "➕ Hisob qo'shish", "ru": "➕ Добавить счёт", "en": "➕ Add account"},
    "btn_rename": {"uz": "✏️ Nomini o'zgartirish", "ru": "✏️ Переименовать", "en": "✏️ Rename"},
    "btn_edit_opening": {
        "uz": "Boshlang'ich qoldiq", "ru": "Начальный остаток", "en": "Opening balance",
    },
    "btn_edit_opening_debt": {
        "uz": "Boshlang'ich qarz", "ru": "Начальный долг", "en": "Opening debt",
    },
    "btn_edit_limit": {"uz": "Kredit limiti", "ru": "Кредитный лимит", "en": "Credit limit"},
    "btn_deactivate": {"uz": "🚫 O'chirish", "ru": "🚫 Отключить", "en": "🚫 Deactivate"},
    "btn_yes_deactivate": {"uz": "Ha, o'chirish", "ru": "Да, отключить", "en": "Yes, deactivate"},
    "btn_edit_amount": {"uz": "Summani o'zgartirish", "ru": "Изменить сумму", "en": "Change amount"},
    "btn_edit_category": {
        "uz": "Kategoriyani o'zgartirish", "ru": "Изменить категорию", "en": "Change category",
    },
    "btn_edit_account": {"uz": "Hisobni o'zgartirish", "ru": "Изменить счёт", "en": "Change account"},
    "btn_delete": {"uz": "🗑 O'chirish", "ru": "🗑 Удалить", "en": "🗑 Delete"},
    "btn_yes_delete": {"uz": "Ha, o'chirish", "ru": "Да, удалить", "en": "Yes, delete"},

    # ---- Expense / income flow ----
    "ask_expense_category": {
        "uz": "Xarajat kategoriyasini tanlang:", "ru": "Выберите категорию расхода:",
        "en": "Choose an expense category:",
    },
    "ask_income_category": {
        "uz": "Daromad manbasini tanlang:", "ru": "Выберите источник дохода:", "en": "Choose the income source:",
    },
    "ask_subcategory": {"uz": "Subkategoriyani tanlang:", "ru": "Выберите подкатегорию:",
                        "en": "Choose a subcategory:"},
    "ask_amount": {
        "uz": "Summani kiriting. Raqam yuboring, masalan 10000 yoki 12500.50:",
        "ru": "Введите сумму. Отправьте число, например 10000 или 12500.50:",
        "en": "Enter the amount. Send a number, e.g. 10000 or 12500.50:",
    },
    "ask_split_amount": {
        "uz": "Xaridning keyingi qismi summasini kiriting:",
        "ru": "Введите сумму следующей части покупки:",
        "en": "Enter the amount of the next part of the purchase:",
    },
    "bad_amount": {
        "uz": "Summani tushunmadim. Musbat son kiriting, masalan 15000 yoki 12500.50.",
        "ru": "Не удалось распознать сумму. Введите положительное число, например 15000 или 12500.50.",
        "en": "Could not read the amount. Enter a positive number, e.g. 15000 or 12500.50.",
    },
    "bad_amount_zero": {
        "uz": "Summani tushunmadim. 0 yoki musbat son kiriting, masalan 0 yoki 250000.",
        "ru": "Не удалось распознать сумму. Введите 0 или положительное число, например 0 или 250000.",
        "en": "Could not read the amount. Enter 0 or a positive number, e.g. 0 or 250000.",
    },
    "ask_currency": {"uz": "Amal valyutasini tanlang:", "ru": "Выберите валюту операции:",
                     "en": "Choose the operation currency:"},
    "no_accounts_in_currency": {
        "uz": "Sizda hali {currency} hisoblari yo'q.",
        "ru": "У вас пока нет счетов в {currency}.",
        "en": "You have no {currency} accounts yet.",
    },
    "ask_account": {
        "uz": "Qaysi hisob? Amal valyutasi: {currency}.",
        "ru": "С какого счёта? Валюта операции: {currency}.",
        "en": "Which account? Operation currency: {currency}.",
    },
    "account_not_found": {"uz": "Hisob topilmadi.", "ru": "Счёт не найден.", "en": "Account not found."},
    "currency_mismatch": {
        "uz": "Hisob valyutasi {account_currency}, amal esa {currency}da.",
        "ru": "Валюта счёта — {account_currency}, а операция в {currency}.",
        "en": "The account currency is {account_currency}, but the operation is in {currency}.",
    },
    "expense_saved": {
        "uz": "Xarajat qismi saqlandi: {amount} · {category} / {subcategory}.\n"
              "Boshqa hisobdan to'lov qo'shasizmi?",
        "ru": "Часть расхода сохранена: {amount} · {category} / {subcategory}.\n"
              "Добавить оплату с другого счёта?",
        "en": "Expense part saved: {amount} · {category} / {subcategory}.\n"
              "Add a payment from another account?",
    },
    "income_saved": {
        "uz": "Daromad saqlandi: +{amount} · {category}.",
        "ru": "Доход сохранён: +{amount} · {category}.",
        "en": "Income saved: +{amount} · {category}.",
    },
    "operation_saved": {"uz": "Amal saqlandi.", "ru": "Операция сохранена.", "en": "Operation saved."},
    "warn_over_limit": {
        "uz": "⚠️ Diqqat: «{name}» bo'yicha qarz {debt} — limitdan ({limit}) oshdi!",
        "ru": "⚠️ Внимание: долг по «{name}» {debt} — превышен лимит ({limit})!",
        "en": "⚠️ Warning: the debt on \"{name}\" is {debt}, above the limit of {limit}!",
    },

    # ---- Report and history ----
    "report_title": {
        "uz": "<b>Hisobot: {start}-dan bugungacha</b>",
        "ru": "<b>Отчёт с {start} по сегодня</b>",
        "en": "<b>Report from {start} to today</b>",
    },
    "report_line": {
        "uz": "{currency}: daromad {income} · xarajat {expense} · farq {net}",
        "ru": "{currency}: доходы {income} · расходы {expense} · итог {net}",
        "en": "{currency}: income {income} · expenses {expense} · net {net}",
    },
    "report_empty": {
        "uz": "Bu davrda hali daromad yoki xarajat yo'q.",
        "ru": "За этот период пока нет доходов и расходов.",
        "en": "No income or expenses in this period yet.",
    },
    "balances": {"uz": "<b>Qoldiqlar:</b>", "ru": "<b>Остатки:</b>", "en": "<b>Balances:</b>"},
    "current_rate": {
        "uz": "Joriy kurs: 1 USD = {rate} UZS", "ru": "Текущий курс: 1 USD = {rate} UZS",
        "en": "Current rate: 1 USD = {rate} UZS",
    },
    "rate_hint": {
        "uz": "Dollar kursini belgilash: /rate 1 USD 12700 UZS",
        "ru": "Чтобы задать курс доллара: /rate 1 USD 12700 UZS",
        "en": "To set the USD rate: /rate 1 USD 12700 UZS",
    },
    "history_empty": {"uz": "Hali amallar yo'q.", "ru": "Операций пока нет.", "en": "No operations yet."},
    "history_title": {
        "uz": "<b>So'nggi amallar</b> (tahrirlash uchun tugmani bosing):",
        "ru": "<b>Последние операции</b> (нажмите, чтобы изменить):",
        "en": "<b>Recent operations</b> (tap one to edit):",
    },
    "line_balance": {"uz": "• {name}: {amount}", "ru": "• {name}: {amount}", "en": "• {name}: {amount}"},
    "line_credit": {
        "uz": "• {name}: qarz {debt}; limit {limit}; mavjud {available}",
        "ru": "• {name}: долг {debt}; лимит {limit}; доступно {available}",
        "en": "• {name}: debt {debt}; limit {limit}; available {available}",
    },
    "line_credit_short": {"uz": "• {name}: qarz {debt}", "ru": "• {name}: долг {debt}",
                          "en": "• {name}: debt {debt}"},

    # ---- Settings ----
    "settings": {
        "uz": "<b>Sozlamalar</b>\n\nMaosh kuni: {salary_day}\n/salaryday 5 — maosh kunini o'zgartirish\n"
              "/rate 1 USD 12700 UZS — dollar kursi",
        "ru": "<b>Настройки</b>\n\nДень зарплаты: {salary_day}\n/salaryday 5 — изменить день зарплаты\n"
              "/rate 1 USD 12700 UZS — курс доллара",
        "en": "<b>Settings</b>\n\nSalary day: {salary_day}\n/salaryday 5 — change the salary day\n"
              "/rate 1 USD 12700 UZS — USD exchange rate",
    },
    "salaryday_usage": {
        "uz": "Maosh kunini 1 dan 28 gacha kiriting. Masalan: /salaryday 5",
        "ru": "Укажите день зарплаты от 1 до 28. Например: /salaryday 5",
        "en": "Enter a salary day from 1 to 28. Example: /salaryday 5",
    },
    "salaryday_saved": {
        "uz": "Moliyaviy oyingiz har oyning {day}-kunidan boshlanadi.",
        "ru": "Ваш финансовый месяц будет начинаться {day}-го числа.",
        "en": "Your financial month will start on day {day}.",
    },
    "rate_usage": {"uz": "Format: /rate 1 USD 12700 UZS", "ru": "Формат: /rate 1 USD 12700 UZS",
                   "en": "Format: /rate 1 USD 12700 UZS"},
    "rate_invalid": {"uz": "Kurs musbat son bo'lishi kerak.", "ru": "Курс должен быть положительным числом.",
                     "en": "The rate must be a positive number."},
    "rate_saved": {"uz": "Kurs saqlandi: 1 USD = {rate} UZS", "ru": "Курс сохранён: 1 USD = {rate} UZS",
                   "en": "Rate saved: 1 USD = {rate} UZS"},

    # ---- Accounts ----
    "accounts_title": {"uz": "<b>Hisoblaringiz:</b>", "ru": "<b>Ваши счета:</b>", "en": "<b>Your accounts:</b>"},
    "accounts_empty": {
        "uz": "Faol hisoblar yo'q. Yangi hisob qo'shing.",
        "ru": "Активных счетов нет. Добавьте новый счёт.",
        "en": "No active accounts. Add a new one.",
    },
    "account_title": {"uz": "<b>{name}</b>", "ru": "<b>{name}</b>", "en": "<b>{name}</b>"},
    "account_kind": {"uz": "Turi: {kind} · {currency}", "ru": "Тип: {kind} · {currency}",
                     "en": "Type: {kind} · {currency}"},
    "account_balance": {"uz": "Qoldiq: {amount}", "ru": "Остаток: {amount}", "en": "Balance: {amount}"},
    "opening_balance": {"uz": "Boshlang'ich qoldiq: {amount}", "ru": "Начальный остаток: {amount}",
                        "en": "Opening balance: {amount}"},
    "credit_debt": {"uz": "Qarz: {amount}", "ru": "Долг: {amount}", "en": "Debt: {amount}"},
    "credit_limit": {"uz": "Limit: {amount}", "ru": "Лимит: {amount}", "en": "Limit: {amount}"},
    "credit_available": {"uz": "Mavjud kredit: {amount}", "ru": "Доступно: {amount}",
                         "en": "Available credit: {amount}"},
    "credit_no_limit": {"uz": "Limit belgilanmagan", "ru": "Лимит не задан", "en": "No limit set"},
    "opening_debt": {"uz": "Boshlang'ich qarz: {amount}", "ru": "Начальный долг: {amount}",
                     "en": "Opening debt: {amount}"},
    "kind_cash": {"uz": "Naqd pul", "ru": "Наличные", "en": "Cash"},
    "kind_debit": {"uz": "Debet karta", "ru": "Дебетовая карта", "en": "Debit card"},
    "kind_credit": {"uz": "Kredit karta", "ru": "Кредитная карта", "en": "Credit card"},
    "ask_account_name": {
        "uz": "Yangi hisob nomini kiriting (40 belgigacha):",
        "ru": "Введите название нового счёта (до 40 символов):",
        "en": "Enter a name for the new account (up to 40 characters):",
    },
    "bad_account_name": {
        "uz": "Nom bo'sh bo'lmasligi va 40 belgidan oshmasligi kerak.",
        "ru": "Название не должно быть пустым и длиннее 40 символов.",
        "en": "The name must be non-empty and at most 40 characters.",
    },
    "ask_account_kind": {"uz": "Hisob turini tanlang:", "ru": "Выберите тип счёта:",
                         "en": "Choose the account type:"},
    "ask_account_currency": {"uz": "Hisob valyutasini tanlang:", "ru": "Выберите валюту счёта:",
                             "en": "Choose the account currency:"},
    "ask_opening_balance": {
        "uz": "Hozirgi qoldiqni kiriting (masalan 250000 yoki 0):",
        "ru": "Введите текущий остаток (например 250000 или 0):",
        "en": "Enter the current balance (e.g. 250000 or 0):",
    },
    "ask_credit_limit": {
        "uz": "Kredit limitini kiriting (limit bo'lmasa 0):",
        "ru": "Введите кредитный лимит (0, если лимита нет):",
        "en": "Enter the credit limit (0 if there is none):",
    },
    "ask_current_debt": {
        "uz": "Kartadagi hozirgi qarzni kiriting (qarz bo'lmasa 0):",
        "ru": "Введите текущий долг по карте (0, если долга нет):",
        "en": "Enter the current debt on the card (0 if none):",
    },
    "account_created": {"uz": "✅ Hisob yaratildi.", "ru": "✅ Счёт создан.", "en": "✅ Account created."},
    "account_updated": {"uz": "✅ Hisob yangilandi.", "ru": "✅ Счёт обновлён.", "en": "✅ Account updated."},
    "ask_new_name": {"uz": "«{name}» uchun yangi nom kiriting:", "ru": "Введите новое название для «{name}»:",
                     "en": "Enter a new name for \"{name}\":"},
    "ask_new_opening": {
        "uz": "«{name}» uchun yangi boshlang'ich qoldiqni kiriting. Joriy qoldiq ham shuncha farqqa o'zgaradi:",
        "ru": "Введите новый начальный остаток для «{name}». Текущий остаток изменится на ту же разницу:",
        "en": "Enter the new opening balance for \"{name}\". The current balance changes by the same difference:",
    },
    "ask_new_opening_debt": {
        "uz": "«{name}» uchun yangi boshlang'ich qarzni kiriting. Joriy qarz ham shuncha farqqa o'zgaradi:",
        "ru": "Введите новый начальный долг для «{name}». Текущий долг изменится на ту же разницу:",
        "en": "Enter the new opening debt for \"{name}\". The current debt changes by the same difference:",
    },
    "ask_new_limit": {
        "uz": "«{name}» uchun yangi kredit limitini kiriting (0 — limitsiz):",
        "ru": "Введите новый кредитный лимит для «{name}» (0 — без лимита):",
        "en": "Enter the new credit limit for \"{name}\" (0 for none):",
    },
    "confirm_deactivate": {
        "uz": "Hisobni o'chirasizmi? U menyulardan yo'qoladi, lekin amallar tarixi saqlanadi.",
        "ru": "Отключить счёт? Он исчезнет из меню, но история операций сохранится.",
        "en": "Deactivate this account? It will disappear from menus, but its history is kept.",
    },
    "account_deactivated": {"uz": "«{name}» hisobi o'chirildi.", "ru": "Счёт «{name}» отключён.",
                            "en": "Account \"{name}\" deactivated."},

    # ---- Transfers ----
    "transfer_need_two": {
        "uz": "O'tkazma uchun kamida ikkita faol hisob kerak.",
        "ru": "Для перевода нужно минимум два активных счёта.",
        "en": "You need at least two active accounts for a transfer.",
    },
    "transfer_from": {"uz": "Qaysi hisobdan o'tkazamiz?", "ru": "С какого счёта перевести?",
                      "en": "Transfer from which account?"},
    "transfer_no_target": {
        "uz": "{currency} valyutasida boshqa hisob yo'q. O'tkazma faqat bir xil valyutadagi hisoblar orasida.",
        "ru": "Нет другого счёта в {currency}. Переводы возможны только между счетами одной валюты.",
        "en": "There is no other {currency} account. Transfers work only between accounts of the same currency.",
    },
    "transfer_to": {
        "uz": "«{name}» hisobidan qaysi hisobga? (kredit kartani tanlasangiz, qarz so'ndiriladi)",
        "ru": "С «{name}» на какой счёт? (выберите кредитную карту, чтобы погасить долг)",
        "en": "From \"{name}\" to which account? (pick a credit card to repay its debt)",
    },
    "transfer_amount": {
        "uz": "O'tkazma summasini kiriting:", "ru": "Введите сумму перевода:", "en": "Enter the transfer amount:",
    },
    "transfer_failed": {
        "uz": "O'tkazmani saqlab bo'lmadi. Qaytadan urinib ko'ring.",
        "ru": "Не удалось сохранить перевод. Попробуйте ещё раз.",
        "en": "Could not save the transfer. Please try again.",
    },
    "transfer_saved": {
        "uz": "✅ O'tkazma saqlandi: {amount} · {source} → {target}",
        "ru": "✅ Перевод сохранён: {amount} · {source} → {target}",
        "en": "✅ Transfer saved: {amount} · {source} → {target}",
    },
    "repayment_saved": {
        "uz": "✅ Kredit karta so'ndirildi: {amount} · {source} → {target}",
        "ru": "✅ Кредитная карта погашена: {amount} · {source} → {target}",
        "en": "✅ Credit card repaid: {amount} · {source} → {target}",
    },

    # ---- Operations (history details, edit, delete) ----
    "op_line": {
        "uz": "{date} {sign}{amount} · {category} · {account}",
        "ru": "{date} {sign}{amount} · {category} · {account}",
        "en": "{date} {sign}{amount} · {category} · {account}",
    },
    "op_transfer": {
        "uz": "{date} 🔁 {amount} · {source} → {target}",
        "ru": "{date} 🔁 {amount} · {source} → {target}",
        "en": "{date} 🔁 {amount} · {source} → {target}",
    },
    "op_repayment": {
        "uz": "{date} 💳 {amount} · {source} → {target} (so'ndirish)",
        "ru": "{date} 💳 {amount} · {source} → {target} (погашение)",
        "en": "{date} 💳 {amount} · {source} → {target} (repayment)",
    },
    "kind_expense_op": {"uz": "Xarajat", "ru": "Расход", "en": "Expense"},
    "kind_income_op": {"uz": "Daromad", "ru": "Доход", "en": "Income"},
    "kind_transfer_op": {"uz": "O'tkazma", "ru": "Перевод", "en": "Transfer"},
    "op_title": {"uz": "<b>{kind}</b>", "ru": "<b>{kind}</b>", "en": "<b>{kind}</b>"},
    "op_amount": {"uz": "Summa: {amount}", "ru": "Сумма: {amount}", "en": "Amount: {amount}"},
    "op_date": {"uz": "Sana: {date}", "ru": "Дата: {date}", "en": "Date: {date}"},
    "op_from": {"uz": "Qayerdan: {name}", "ru": "Откуда: {name}", "en": "From: {name}"},
    "op_to": {"uz": "Qayerga: {name}", "ru": "Куда: {name}", "en": "To: {name}"},
    "op_category": {"uz": "Kategoriya: {category} / {subcategory}", "ru": "Категория: {category} / {subcategory}",
                    "en": "Category: {category} / {subcategory}"},
    "op_account": {"uz": "Hisob: {name}", "ru": "Счёт: {name}", "en": "Account: {name}"},
    "op_note": {"uz": "Izoh: {note}", "ru": "Заметка: {note}", "en": "Note: {note}"},
    "operation_updated": {"uz": "✅ Amal yangilandi.", "ru": "✅ Операция обновлена.", "en": "✅ Operation updated."},
    "operation_not_found": {"uz": "Amal topilmadi.", "ru": "Операция не найдена.", "en": "Operation not found."},
    "ask_new_amount": {"uz": "Yangi summani kiriting:", "ru": "Введите новую сумму:", "en": "Enter the new amount:"},
    "ask_new_category": {"uz": "Yangi kategoriyani tanlang:", "ru": "Выберите новую категорию:",
                         "en": "Choose the new category:"},
    "ask_new_account": {
        "uz": "Yangi hisobni tanlang ({currency}):", "ru": "Выберите новый счёт ({currency}):",
        "en": "Choose the new account ({currency}):",
    },
    "confirm_delete": {
        "uz": "Bu amalni o'chirasizmi? Hisob qoldig'i qayta hisoblanadi.",
        "ru": "Удалить эту операцию? Остаток счёта будет пересчитан.",
        "en": "Delete this operation? The account balance will be recalculated.",
    },
    "confirm_delete_transfer": {
        "uz": "Bu o'tkazmani o'chirasizmi? Ikkala hisob qoldig'i ham qayta hisoblanadi.",
        "ru": "Удалить этот перевод? Остатки обоих счетов будут пересчитаны.",
        "en": "Delete this transfer? Both account balances will be recalculated.",
    },
    "operation_deleted": {
        "uz": "🗑 Amal o'chirildi. Yangi qoldiqlar:", "ru": "🗑 Операция удалена. Новые остатки:",
        "en": "🗑 Operation deleted. New balances:",
    },

    # ---- AI input (receipts, voice, free text, bank SMS) ----
    "ai_not_configured": {
        "uz": "🤖 AI kiritish sozlanmagan (GEMINI_API_KEY yo'q). Menyudan foydalaning.",
        "ru": "🤖 AI-ввод не настроен (нет GEMINI_API_KEY). Воспользуйтесь меню.",
        "en": "🤖 AI input is not configured (no GEMINI_API_KEY). Please use the menu.",
    },
    "ai_analyzing": {"uz": "⏳ Tahlil qilinmoqda...", "ru": "⏳ Анализирую...", "en": "⏳ Analyzing..."},
    "ai_nothing_found": {
        "uz": "🤖 Bu xabarda amal topilmadi. Aniqroq yozing (masalan: «taksi 25000 uob») "
              "yoki menyudan foydalaning.",
        "ru": "🤖 Не нашёл операций в сообщении. Напишите точнее (например: «такси 25000 uob») "
              "или воспользуйтесь меню.",
        "en": "🤖 No operation found in this message. Try again (e.g. \"taxi 25000 uob\") or use the menu.",
    },
    "ai_unsupported_file": {
        "uz": "Bu fayl turini o'qiy olmayman. Rasm, PDF yoki ovozli xabar yuboring.",
        "ru": "Не могу прочитать этот тип файла. Отправьте фото, PDF или голосовое сообщение.",
        "en": "I can't read this file type. Send a photo, a PDF or a voice message.",
    },
    "ai_error_timeout": {
        "uz": "⌛ AI vaqtida javob bermadi. Birozdan so'ng qayta urinib ko'ring.",
        "ru": "⌛ AI не ответил вовремя. Попробуйте ещё раз чуть позже.",
        "en": "⌛ The AI did not answer in time. Please try again a bit later.",
    },
    "ai_error_quota": {
        "uz": "🚦 AI so'rovlar limiti tugadi. Keyinroq urinib ko'ring yoki menyudan foydalaning.",
        "ru": "🚦 Исчерпан лимит запросов к AI. Попробуйте позже или воспользуйтесь меню.",
        "en": "🚦 The AI request quota is exhausted. Try later or use the menu.",
    },
    "ai_error_auth": {
        "uz": "🔑 GEMINI_API_KEY noto'g'ri yoki unga ruxsat yo'q.",
        "ru": "🔑 GEMINI_API_KEY неверный или не имеет доступа.",
        "en": "🔑 GEMINI_API_KEY is invalid or has no access.",
    },
    "ai_error_bad_input": {
        "uz": "AI bu faylni o'qiy olmadi. Boshqa rasm yuboring yoki matn bilan yozing.",
        "ru": "AI не смог прочитать этот файл. Отправьте другое фото или напишите текстом.",
        "en": "The AI could not read this file. Send another photo or type it as text.",
    },
    "ai_error_unavailable": {
        "uz": "AI xizmati hozir ishlamayapti. Keyinroq urinib ko'ring.",
        "ru": "Сервис AI сейчас недоступен. Попробуйте позже.",
        "en": "The AI service is unavailable right now. Please try later.",
    },
    "ai_error_bad_response": {
        "uz": "AI tushunarsiz javob qaytardi. Qayta urinib ko'ring.",
        "ru": "AI вернул непонятный ответ. Попробуйте ещё раз.",
        "en": "The AI returned an unreadable answer. Please try again.",
    },
    "ai_error_too_large": {
        "uz": "Fayl juda katta (15 MB gacha).", "ru": "Файл слишком большой (до 15 МБ).",
        "en": "The file is too large (up to 15 MB).",
    },
    "ai_draft_title": {
        "uz": "🤖 <b>Qoralama {index}/{total}</b> · {kind}", "ru": "🤖 <b>Черновик {index}/{total}</b> · {kind}",
        "en": "🤖 <b>Draft {index}/{total}</b> · {kind}",
    },
    "ai_date_now": {"uz": "hozir", "ru": "сейчас", "en": "now"},
    "ai_missing": {"uz": "✍️ To'ldiring: {fields}", "ru": "✍️ Заполните: {fields}", "en": "✍️ Please fill in: {fields}"},
    "ai_field_amount": {"uz": "summa", "ru": "сумма", "en": "amount"},
    "ai_field_currency": {"uz": "valyuta", "ru": "валюта", "en": "currency"},
    "ai_field_account": {"uz": "hisob", "ru": "счёт", "en": "account"},
    "ai_field_to_account": {"uz": "qabul qiluvchi hisob", "ru": "счёт получателя", "en": "receiving account"},
    "ai_field_category": {"uz": "kategoriya", "ru": "категория", "en": "category"},
    "ai_duplicate": {
        "uz": "⚠️ Shunga o'xshash amal allaqachon saqlangan (o'sha summa va hisob yoki o'sha xabar). "
              "Ikki marta yozmayotganingizni tekshiring.",
        "ru": "⚠️ Похожая операция уже сохранена (та же сумма и счёт или то же сообщение). "
              "Проверьте, чтобы не записать дважды.",
        "en": "⚠️ A similar operation is already saved (same amount and account, or the same message). "
              "Make sure you are not recording it twice.",
    },
    "ai_low_confidence": {
        "uz": "🤔 AI ishonchi past — ma'lumotlarni tekshiring.", "ru": "🤔 AI не уверен — проверьте данные.",
        "en": "🤔 The AI is not sure — please check the details.",
    },
    "ai_note_amount": {
        "uz": "ℹ️ Summani aniqlab bo'lmadi.", "ru": "ℹ️ Не удалось распознать сумму.",
        "en": "ℹ️ The amount could not be recognized.",
    },
    "ai_note_currency": {
        "uz": "ℹ️ Valyuta qo'llab-quvvatlanmaydi — UZS yoki USD ni tanlang.",
        "ru": "ℹ️ Валюта не поддерживается — выберите UZS или USD.",
        "en": "ℹ️ Unsupported currency — choose UZS or USD.",
    },
    "ai_note_account_currency": {
        "uz": "ℹ️ Topilgan hisob valyutasi mos emas — hisobni tanlang.",
        "ru": "ℹ️ Валюта найденного счёта не совпадает — выберите счёт.",
        "en": "ℹ️ The matched account has a different currency — choose an account.",
    },
    "btn_ai_save": {"uz": "✅ Saqlash", "ru": "✅ Сохранить", "en": "✅ Save"},
    "btn_ai_save_all": {"uz": "✅ Hammasini saqlash", "ru": "✅ Сохранить все", "en": "✅ Save all"},
    "btn_ai_skip": {"uz": "⏭ O'tkazib yuborish", "ru": "⏭ Пропустить", "en": "⏭ Skip"},
    "btn_ai_cancel": {"uz": "❌ Bekor qilish", "ru": "❌ Отмена", "en": "❌ Cancel"},
    "btn_ai_amount": {"uz": "✏️ Summa", "ru": "✏️ Сумма", "en": "✏️ Amount"},
    "btn_ai_category": {"uz": "✏️ Kategoriya", "ru": "✏️ Категория", "en": "✏️ Category"},
    "btn_ai_account": {"uz": "✏️ Hisob", "ru": "✏️ Счёт", "en": "✏️ Account"},
    "btn_ai_to_account": {"uz": "✏️ Qayerga", "ru": "✏️ Куда", "en": "✏️ To account"},
    "btn_ai_kind": {"uz": "✏️ Turi", "ru": "✏️ Тип", "en": "✏️ Type"},
    "btn_ai_currency": {"uz": "✏️ Valyuta", "ru": "✏️ Валюта", "en": "✏️ Currency"},
    "btn_ai_date": {"uz": "✏️ Sana", "ru": "✏️ Дата", "en": "✏️ Date"},
    "ai_ask_kind": {"uz": "Amal turini tanlang:", "ru": "Выберите тип операции:", "en": "Choose the operation type:"},
    "ai_ask_to_account": {
        "uz": "Qaysi hisobga o'tkaziladi ({currency})?", "ru": "На какой счёт перевод ({currency})?",
        "en": "Which account receives the money ({currency})?",
    },
    "ai_ask_date": {
        "uz": "Sanani kiriting: 04.11.2026 yoki 04.11.2026 14:30",
        "ru": "Введите дату: 04.11.2026 или 04.11.2026 14:30",
        "en": "Enter the date: 04.11.2026 or 04.11.2026 14:30",
    },
    "ai_bad_date": {
        "uz": "Sana noto'g'ri. Format: 04.11.2026 14:30 (oxirgi bir yil ichida).",
        "ru": "Неверная дата. Формат: 04.11.2026 14:30 (в пределах последнего года).",
        "en": "Invalid date. Format: 04.11.2026 14:30 (within the last year).",
    },
    "ai_saved": {"uz": "✅ Saqlandi: {summary}", "ru": "✅ Сохранено: {summary}", "en": "✅ Saved: {summary}"},
    "ai_skipped": {"uz": "⏭ O'tkazib yuborildi.", "ru": "⏭ Пропущено.", "en": "⏭ Skipped."},
    "ai_save_failed": {
        "uz": "Saqlab bo'lmadi: hisob topilmadi yoki valyuta mos emas. Hisobni qayta tanlang.",
        "ru": "Не удалось сохранить: счёт не найден или валюта не совпадает. Выберите счёт заново.",
        "en": "Could not save: the account was not found or its currency differs. Choose the account again.",
    },
}
