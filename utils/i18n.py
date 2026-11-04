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
        "uz": "<b>MOLIYA BOTI</b>\n\nXarajat yoki daromadni shunchaki yozing yoki ovozli xabar yuboring, masalan: "
              "«taksi 25000 naqd». Chek rasmi yoki bank SMS'ini ham yuborishingiz mumkin — bot darhol saqlaydi.\n\n"
              "Pastdagi tugmalar: 📊 Hisobot, 💳 Balans, ⚙️ Sozlamalar.\n"
              "Maosh kuni: /salaryday 5 · Dollar kursi: /rate",
        "ru": "<b>ФИНАНСОВЫЙ БОТ</b>\n\nПросто напишите или наговорите расход или доход, например: "
              "«такси 25000 наличными». Можно прислать фото чека или банковское SMS — бот сразу сохранит.\n\n"
              "Кнопки внизу: 📊 Отчёт, 💳 Баланс, ⚙️ Настройки.\n"
              "День зарплаты: /salaryday 5 · Курс доллара: /rate",
        "en": "<b>FINANCE BOT</b>\n\nJust type or say an expense or income, e.g. \"taxi 25000 cash\". "
              "You can also send a receipt photo or a bank SMS — the bot saves it right away.\n\n"
              "Buttons below: 📊 Report, 💳 Balance, ⚙️ Settings.\n"
              "Salary day: /salaryday 5 · USD rate: /rate",
    },
    "bot_started": {"uz": "Bot ishga tushdi", "ru": "Бот запущен", "en": "Bot has started"},
    "cmd_start": {"uz": "Boshlash", "ru": "Начало", "en": "Start"},
    "cmd_expense": {"uz": "Xarajatni qo'lda kiritish", "ru": "Ввести расход вручную", "en": "Add an expense manually"},
    "cmd_income": {"uz": "Daromadni qo'lda kiritish", "ru": "Ввести доход вручную", "en": "Add an income manually"},
    "cmd_transfer": {"uz": "Hisoblar orasida o'tkazma", "ru": "Перевод между счетами",
                     "en": "Transfer between accounts"},
    "cmd_salaryday": {"uz": "Maosh kuni, masalan /salaryday 5", "ru": "День зарплаты, например /salaryday 5",
                      "en": "Set salary day, e.g. /salaryday 5"},
    "cmd_rate": {"uz": "Dollar kursi (Markaziy bank) yoki o'zingiznikini belgilash",
                 "ru": "Курс доллара (Центробанк) или свой курс",
                 "en": "USD rate (Central Bank) or set your own"},
    "cmd_settings": {"uz": "Sozlamalar", "ru": "Настройки", "en": "Settings"},
    "cmd_report": {"uz": "Hisobot", "ru": "Отчёт", "en": "Report"},
    "cmd_balance": {"uz": "Hisoblar balansi", "ru": "Баланс счетов", "en": "Account balances"},
    "cmd_help": {"uz": "Yordam", "ru": "Помощь", "en": "Help"},
    "language_changed": {
        "uz": "Til o'zgartirildi: o'zbekcha.",
        "ru": "Язык изменён: русский.",
        "en": "Language changed: English.",
    },
    "help": {
        "uz": "<b>Buyruqlar</b>\n"
              "/start — boshlash\n"
              "/expense — xarajatni qo'lda kiritish (xaridni bir nechta hisobdan to'lash mumkin)\n"
              "/income — daromadni qo'lda kiritish\n"
              "/transfer — o'z hisoblaringiz orasida o'tkazma, kredit kartani so'ndirish\n"
              "/salaryday 5 — moliyaviy oy boshlanadigan kun (1–28)\n"
              "/rate — dollar kursi (Markaziy bank kursi; o'zgartirish: /rate 1 USD 12850 UZS, qaytarish: /rate auto)\n"
              "/help — yordam\n\n"
              "<b>🤖 Amal qo'shish</b>\n"
              "Shunchaki yozing yoki ayting: «taksi 25000 naqd», «kofe 18 ming», «maosh 12m hamkorbankka». "
              "Chek rasmi, PDF yoki bank SMS'ini ham yuborish mumkin. Bot amalni darhol saqlaydi: to'lov usuli "
              "aniq bo'lmasa, faqat shuni so'raydi; kategoriya aniq bo'lmasa, «Boshqa» ga yoziladi. "
              "Ovozli xabar 2 daqiqagacha bo'lishi kerak va faqat Google Gemini bilan ishlaydi. "
              "Rasm, ovoz va matn tahlil uchun AI xizmatiga (Google Gemini yoki Anthropic Claude) yuboriladi.\n\n"
              "<b>Pastdagi tugmalar</b>\n"
              "📊 Hisobot — moliyaviy oy: daromad, xarajat, kategoriyalar va oldingi davr bilan solishtirish; "
              "kategoriyani bosing — subkategoriyalar; ◀ ▶ — boshqa davrlar (o'tkazmalar hisobga olinmaydi)\n"
              "💳 Balans — hisoblar qoldig'i, kredit limiti va qarz\n"
              "⚙️ Sozlamalar — hisoblar, byudjetlar, tarix (amalni tahrirlash yoki o'chirish), AI maslahatlari "
              "va til\n\n"
              "<b>🎯 Byudjetlar va ogohlantirishlar</b>\n"
              "Sozlamalar → Byudjetlar: kategoriya uchun oylik limit. Limitning yoki kredit karta limitining "
              "80% va 100% ga yetganda bot xabar yuboradi (har bir davrda har biri bir marta).\n\n"
              "<b>💬 Savollar va maslahatlar</b>\n"
              "Savolni shunchaki yozing (masalan «bu oy taksiga qancha ketdi?»). Har dushanba 09:00 da haftalik "
              "xulosa, yangi moliyaviy oy boshlanganda 09:00 da oylik xulosa keladi; Sozlamalar → AI "
              "maslahatlari'da o'chirish mumkin. Savollar va hisob-kitob xulosalari AI xizmatiga yuboriladi.",
        "ru": "<b>Команды</b>\n"
              "/start — начало\n"
              "/expense — ввести расход вручную (покупку можно оплатить с нескольких счетов)\n"
              "/income — ввести доход вручную\n"
              "/transfer — перевод между своими счетами, погашение кредитной карты\n"
              "/salaryday 5 — день начала финансового месяца (1–28)\n"
              "/rate — курс доллара (курс Центробанка; свой курс: /rate 1 USD 12850 UZS, вернуть: /rate auto)\n"
              "/help — помощь\n\n"
              "<b>🤖 Добавить операцию</b>\n"
              "Просто напишите или наговорите: «такси 25000 наличными», «кофе 18 тысяч», «зарплата 12м на "
              "hamkorbank». Можно отправить фото или PDF чека или банковское SMS. Бот сразу сохраняет операцию: "
              "если непонятен способ оплаты, спросит только его; если непонятна категория, запишет в «Прочее». "
              "Голосовые — до 2 минут, работают только с Google Gemini. "
              "Фото, голос и текст отправляются на анализ в AI-сервис (Google Gemini или Anthropic Claude).\n\n"
              "<b>Кнопки внизу</b>\n"
              "📊 Отчёт — финансовый месяц: доходы, расходы, категории и сравнение с прошлым периодом; нажмите "
              "категорию — подкатегории; ◀ ▶ — другие периоды (переводы не учитываются)\n"
              "💳 Баланс — остатки счетов, кредитный лимит и долг\n"
              "⚙️ Настройки — счета, бюджеты, история (изменить или удалить операцию), AI-советы и язык\n\n"
              "<b>🎯 Бюджеты и предупреждения</b>\n"
              "Настройки → Бюджеты: месячный лимит на категорию. Бот напишет, когда лимит или кредитный лимит "
              "карты дойдёт до 80% и 100% (по одному разу за период).\n\n"
              "<b>💬 Вопросы и советы</b>\n"
              "Просто напишите вопрос (например «сколько я потратил на такси в этом месяце?»). Каждый понедельник "
              "в 09:00 приходит недельная сводка, а в 09:00 в первый день нового финансового месяца — месячная; "
              "отключить: Настройки → AI-советы. Вопросы и сводки по вашим данным отправляются в AI-сервис.",
        "en": "<b>Commands</b>\n"
              "/start — start\n"
              "/expense — add an expense manually (a purchase can be paid from several accounts)\n"
              "/income — add an income manually\n"
              "/transfer — transfer between your own accounts, repay a credit card\n"
              "/salaryday 5 — day your financial month starts (1–28)\n"
              "/rate — USD rate (Central Bank rate; your own: /rate 1 USD 12850 UZS, undo: /rate auto)\n"
              "/help — help\n\n"
              "<b>🤖 AI input: adding operations</b>\n"
              "Just type or say it: \"taxi 25000 cash\", \"coffee 18k\", \"got salary 12m to hamkorbank\". "
              "You can also send a receipt photo or PDF or a bank SMS. The bot saves the operation right away: if "
              "the payment method is unclear it asks only for that; an unclear category goes to \"Other\". "
              "Voice messages can be up to 2 minutes and work with Google Gemini only. "
              "Photos, voice and text are sent to the AI service (Google Gemini or Anthropic Claude) for "
              "analysis.\n\n"
              "<b>Buttons below</b>\n"
              "📊 Report — the financial month: income, expenses, categories and a comparison with the previous "
              "period; tap a category for subcategories; ◀ ▶ for other periods (transfers are not counted)\n"
              "💳 Balance — account balances, credit limit and debt\n"
              "⚙️ Settings — accounts, budgets, history (edit or delete an operation), AI advice and language\n\n"
              "<b>🎯 Budgets and alerts</b>\n"
              "Settings → Budgets: a monthly limit per category. The bot messages you when a budget or a credit "
              "card limit reaches 80% and 100% (once per period each).\n\n"
              "<b>💬 Questions and advice</b>\n"
              "Just type a question (e.g. \"how much did I spend on taxi this month?\"). A weekly summary arrives "
              "every Monday at 09:00 and a monthly review at 09:00 on the first day of a new financial month; turn "
              "them off in Settings → AI advice. Questions and summaries of your data are sent to the AI service.",
    },
    "use_menu": {
        "uz": "Amalni yozing (masalan «taksi 25000 naqd») yoki pastdagi tugmalardan foydalaning.",
        "ru": "Напишите операцию (например «такси 25000 наличными») или воспользуйтесь кнопками внизу.",
        "en": "Write an operation (e.g. \"taxi 25000 cash\") or use the buttons below.",
    },
    "session_lost": {
        "uz": "Sessiya tugadi. Qaytadan boshlang: /start",
        "ru": "Сессия истекла. Начните заново: /start",
        "en": "Session expired. Start again: /start",
    },
    "cancelled": {"uz": "Bekor qilindi.", "ru": "Отменено.", "en": "Cancelled."},

    # ---- Buttons ----
    "btn_accounts": {"uz": "💳 HISOBLAR", "ru": "💳 СЧЕТА", "en": "💳 ACCOUNTS"},
    "btn_history": {"uz": "🧾 TARIX", "ru": "🧾 ИСТОРИЯ", "en": "🧾 HISTORY"},
    "btn_cancel": {"uz": "Bekor qilish", "ru": "Отмена", "en": "Cancel"},
    "kb_report": {"uz": "📊 Hisobot", "ru": "📊 Отчёт", "en": "📊 Report"},
    "kb_balance": {"uz": "💳 Balans", "ru": "💳 Баланс", "en": "💳 Balance"},
    "kb_settings": {"uz": "⚙️ Sozlamalar", "ru": "⚙️ Настройки", "en": "⚙️ Settings"},
    "btn_back": {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад", "en": "⬅️ Back"},
    "btn_language": {"uz": "🌐 Til", "ru": "🌐 Язык", "en": "🌐 Language"},
    "btn_no_subcategory": {"uz": "Subkategoriyasiz", "ru": "Без подкатегории", "en": "No subcategory"},
    "btn_split_more": {
        "uz": "Ha, yana bir qism qo'shish", "ru": "Да, добавить ещё часть", "en": "Yes, add another part",
    },
    "btn_split_finish": {"uz": "Yo'q, yakunlash", "ru": "Нет, завершить", "en": "No, finish"},
    "btn_add_account": {"uz": "➕ Hisob qo'shish", "ru": "➕ Добавить счёт", "en": "➕ Add account"},
    "btn_miniapp": {"uz": "💳 Kartalarim (Mini App)", "ru": "💳 Мои карты (Mini App)", "en": "💳 My cards (Mini App)"},
    "menu_miniapp": {"uz": "Kartalarim", "ru": "Мои карты", "en": "My cards"},
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
    "ask_split_more": {
        "uz": "Boshqa hisobdan ham to'lov qo'shasizmi?", "ru": "Добавить оплату с другого счёта?",
        "en": "Add a payment from another account?",
    },
    "warn_over_limit": {
        "uz": "⚠️ Diqqat: «{name}» bo'yicha qarz {debt} — limitdan ({limit}) oshdi!",
        "ru": "⚠️ Внимание: долг по «{name}» {debt} — превышен лимит ({limit})!",
        "en": "⚠️ Warning: the debt on \"{name}\" is {debt}, above the limit of {limit}!",
    },

    # ---- Saved operation card (utils/misc/texts.operation_card) ----
    "opcard_expense": {"uz": "💸 <b>XARAJAT</b>", "ru": "💸 <b>РАСХОД</b>", "en": "💸 <b>EXPENSE</b>"},
    "opcard_income": {"uz": "💰 <b>KIRIM</b>", "ru": "💰 <b>ДОХОД</b>", "en": "💰 <b>INCOME</b>"},
    "opcard_transfer": {"uz": "🔁 <b>O'TKAZMA</b>", "ru": "🔁 <b>ПЕРЕВОД</b>", "en": "🔁 <b>TRANSFER</b>"},
    "opcard_amount": {"uz": "💰 <b>Summa:</b> {amount}", "ru": "💰 <b>Сумма:</b> {amount}",
                      "en": "💰 <b>Amount:</b> {amount}"},
    "opcard_category": {"uz": "🏷 <b>Kategoriya:</b> {category}", "ru": "🏷 <b>Категория:</b> {category}",
                        "en": "🏷 <b>Category:</b> {category}"},
    "opcard_payment": {"uz": "💳 <b>To'lov:</b> {name}", "ru": "💳 <b>Оплата:</b> {name}",
                       "en": "💳 <b>Paid with:</b> {name}"},
    "opcard_account": {"uz": "💳 <b>Hisob:</b> {name}", "ru": "💳 <b>Счёт:</b> {name}",
                       "en": "💳 <b>Account:</b> {name}"},
    "opcard_from": {"uz": "📤 <b>Qayerdan:</b> {name}", "ru": "📤 <b>Откуда:</b> {name}",
                    "en": "📤 <b>From:</b> {name}"},
    "opcard_to": {"uz": "📥 <b>Qayerga:</b> {name}", "ru": "📥 <b>Куда:</b> {name}", "en": "📥 <b>To:</b> {name}"},
    "opcard_time": {"uz": "🕐 <b>Vaqt:</b> {time}", "ru": "🕐 <b>Время:</b> {time}", "en": "🕐 <b>Time:</b> {time}"},
    "months_short": {
        "uz": "Yan Fev Mar Apr May Iyn Iyl Avg Sen Okt Noy Dek",
        "ru": "янв фев мар апр мая июн июл авг сен окт ноя дек",
        "en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
    },

    # ---- Report and history ----
    "report_empty": {
        "uz": "Bu davrda hali daromad yoki xarajat yo'q.",
        "ru": "За этот период пока нет доходов и расходов.",
        "en": "No income or expenses in this period yet.",
    },
    "rate_hint": {
        "uz": "Dollar kursi hozircha noma'lum. O'zingiznikini belgilash: /rate 1 USD 12850 UZS",
        "ru": "Курс доллара пока неизвестен. Чтобы задать свой: /rate 1 USD 12850 UZS",
        "en": "To set the USD rate: /rate",
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
              "/rate — dollar kursi (Markaziy bank; o'zingiznikini: /rate 1 USD 12850 UZS, qaytarish: /rate auto)",
        "ru": "<b>Настройки</b>\n\nДень зарплаты: {salary_day}\n/salaryday 5 — изменить день зарплаты\n"
              "/rate — курс доллара (Центробанк; свой: /rate 1 USD 12850 UZS, вернуть: /rate auto)",
        "en": "<b>Settings</b>\n\nSalary day: {salary_day}\n/salaryday 5 — change the salary day\n"
              "/rate — USD rate (Central Bank; your own: /rate 1 USD 12850 UZS, undo: /rate auto)",
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
    "rate_usage": {
        "uz": "Format: /rate 1 USD 12850 UZS\nHozirgi kurs: /rate · Markaziy bank kursiga qaytish: /rate auto",
        "ru": "Формат: /rate 1 USD 12850 UZS\nТекущий курс: /rate · Вернуть курс Центробанка: /rate auto",
        "en": "Format: /rate 1 USD 12850 UZS\nCurrent rate: /rate · Back to the Central Bank rate: /rate auto",
    },
    "rate_source_cbu": {"uz": "Markaziy bank, {date}", "ru": "Центральный банк, {date}",
                        "en": "Central Bank, {date}"},
    "rate_source_manual": {"uz": "qo'lda", "ru": "вручную", "en": "manual"},
    "rate_current": {
        "uz": "Dollar kursi: 1 USD = {rate} UZS ({source})\n\n/rate 1 USD 12850 UZS — o'zingiznikini belgilash\n"
              "/rate auto — Markaziy bank kursiga qaytish",
        "ru": "Курс доллара: 1 USD = {rate} UZS ({source})\n\n/rate 1 USD 12850 UZS — задать свой курс\n"
              "/rate auto — вернуть курс Центробанка",
        "en": "USD rate: 1 USD = {rate} UZS ({source})\n\n/rate 1 USD 12850 UZS — set your own rate\n"
              "/rate auto — back to the Central Bank rate",
    },
    "rate_unknown": {
        "uz": "Markaziy bank kursini hozircha olib bo'lmadi. Keyinroq urinib ko'ring yoki o'zingiznikini "
              "belgilang: /rate 1 USD 12850 UZS",
        "ru": "Курс Центробанка пока получить не удалось. Попробуйте позже или задайте свой: "
              "/rate 1 USD 12850 UZS",
        "en": "The Central Bank rate could not be fetched yet. Try later or set your own: "
              "/rate 1 USD 12850 UZS",
    },
    "rate_auto": {
        "uz": "Endi Markaziy bank kursi ishlatiladi.", "ru": "Теперь используется курс Центробанка.",
        "en": "The Central Bank rate is used again.",
    },
    "rate_auto_none": {
        "uz": "O'z kursingiz belgilanmagan, Markaziy bank kursi ishlatilmoqda.",
        "ru": "Свой курс не задан, используется курс Центробанка.",
        "en": "You have no own rate set; the Central Bank rate is used.",
    },
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
        "uz": "🤖 AI kiritish sozlanmagan ({env_key} yo'q). Qo'lda kiriting: /expense, /income, /transfer.",
        "ru": "🤖 AI-ввод не настроен (нет {env_key}). Введите вручную: /expense, /income, /transfer.",
        "en": "🤖 AI input is not configured (no {env_key}). Enter it manually: /expense, /income, /transfer.",
    },
    "ai_analyzing": {"uz": "⏳ Tahlil qilinmoqda...", "ru": "⏳ Анализирую...", "en": "⏳ Analyzing..."},
    "ai_nothing_found": {
        "uz": "🤖 Bu xabarda amal topilmadi. Aniqroq yozing, masalan: «taksi 25000 naqd».",
        "ru": "🤖 Не нашёл операций в сообщении. Напишите точнее, например: «такси 25000 наличными».",
        "en": "🤖 No operation found in this message. Try again, e.g. \"taxi 25000 cash\".",
    },
    "ai_unsupported_file": {
        "uz": "Bu fayl turini o'qiy olmayman. Rasm, PDF yoki ovozli xabar yuboring.",
        "ru": "Не могу прочитать этот тип файла. Отправьте фото, PDF или голосовое сообщение.",
        "en": "I can't read this file type. Send a photo, a PDF or a voice message.",
    },
    "ai_voice_needs_gemini": {
        "uz": "🎤 Ovozli xabarlarni faqat Google Gemini tushunadi (AI_PROVIDER=gemini). "
              "Hozircha matn yoki chek rasmini yuboring.",
        "ru": "🎤 Голосовые сообщения понимает только Google Gemini (AI_PROVIDER=gemini). "
              "Пока отправьте текст или фото чека.",
        "en": "🎤 Voice messages need Google Gemini (AI_PROVIDER=gemini). "
              "For now, send text or a photo of the receipt.",
    },
    "ai_voice_too_long": {
        "uz": "🎤 Ovozli xabar juda uzun: {minutes} daqiqagacha va {mb} MB gacha bo'lsin. "
              "Qisqaroq yozib yuboring yoki matn bilan yozing.",
        "ru": "🎤 Голосовое слишком длинное: до {minutes} минут и до {mb} МБ. "
              "Запишите покороче или напишите текстом.",
        "en": "🎤 The voice message is too long: up to {minutes} minutes and {mb} MB. "
              "Record a shorter one or type it as text.",
    },
    "ai_video_note_unsupported": {
        "uz": "📹 Video xabarlarni o'qimayman. Ovozli xabar, matn yoki chek rasmini yuboring.",
        "ru": "📹 Видеосообщения не поддерживаются. Отправьте голосовое, текст или фото чека.",
        "en": "📹 Video notes are not supported. Send a voice message, text or a photo of the receipt.",
    },
    "ai_error_refused": {
        "uz": "AI bu so'rovni bajarishdan bosh tortdi. Boshqa rasm yoki matn yuboring.",
        "ru": "AI отказался обрабатывать этот запрос. Отправьте другое фото или текст.",
        "en": "The AI declined to process this request. Try a different photo or text.",
    },
    "ai_error_timeout": {
        "uz": "⌛ AI vaqtida javob bermadi. Birozdan so'ng qayta urinib ko'ring.",
        "ru": "⌛ AI не ответил вовремя. Попробуйте ещё раз чуть позже.",
        "en": "⌛ The AI did not answer in time. Please try again a bit later.",
    },
    "ai_error_quota": {
        "uz": "🚦 AI so'rovlar limiti tugadi. Keyinroq urinib ko'ring yoki qo'lda kiriting: /expense.",
        "ru": "🚦 Исчерпан лимит запросов к AI. Попробуйте позже или введите вручную: /expense.",
        "en": "🚦 The AI request quota is exhausted. Try later or enter it manually: /expense.",
    },
    "ai_error_auth": {
        "uz": "🔑 {env_key} noto'g'ri yoki unga ruxsat yo'q.",
        "ru": "🔑 {env_key} неверный или не имеет доступа.",
        "en": "🔑 {env_key} is invalid or has no access.",
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
        "uz": "Fayl juda katta (rasm 5 MB gacha, PDF 14 MB gacha).",
        "ru": "Файл слишком большой (фото до 5 МБ, PDF до 14 МБ).",
        "en": "The file is too large (images up to 5 MB, PDFs up to 14 MB).",
    },
    "ai_ask_account": {
        "uz": "💳 Qaysi to'lov usuli?", "ru": "💳 Какой способ оплаты?", "en": "💳 Which payment method?",
    },
    "ai_pick_account": {
        "uz": "💳 Tugmalardan birini tanlang yoki ➕ yangi karta qo'shing.",
        "ru": "💳 Выберите одну из кнопок или ➕ добавьте новую карту.",
        "en": "💳 Pick one of the buttons or ➕ add a new card.",
    },
    "btn_ai_new_account": {
        "uz": "➕ Yangi karta qo'shish", "ru": "➕ Добавить новую карту", "en": "➕ Add a new card",
    },
    "ai_no_amount": {
        "uz": "🤖 Summani tushunmadim. Masalan: «taksi 25000 naqd».",
        "ru": "🤖 Не понял сумму. Например: «такси 25000 наличными».",
        "en": "🤖 I could not find an amount. Example: \"taxi 25000 cash\".",
    },
    "ai_no_target": {
        "uz": "🤖 O'tkazma qaysi hisobga ekanini tushunmadim. /transfer orqali kiriting.",
        "ru": "🤖 Не понял, на какой счёт перевод. Введите его через /transfer.",
        "en": "🤖 I could not tell which account the transfer goes to. Use /transfer.",
    },
    "ai_already_saved": {
        "uz": "⏭ Bu xabar yoki fayl allaqachon saqlangan — qayta yozilmadi.",
        "ru": "⏭ Это сообщение или файл уже сохранены — повторно не записано.",
        "en": "⏭ This message or file was already saved — not recorded again.",
    },
    "ai_duplicate": {
        "uz": "⚠️ Yaqinda shu hisobdan xuddi shunday summa yozilgan. Ikki marta yozilgan bo'lsa, o'chiring: "
              "⚙️ Sozlamalar → 🧾 Tarix.",
        "ru": "⚠️ Недавно с этого счёта уже записана такая же сумма. Если это дубль, удалите его: "
              "⚙️ Настройки → 🧾 История.",
        "en": "⚠️ The same amount on this account was recorded a few minutes ago. If it is a duplicate, delete "
              "it: ⚙️ Settings → 🧾 History.",
    },
    "ai_save_failed": {
        "uz": "Saqlab bo'lmadi: hisob topilmadi yoki valyuta mos emas.",
        "ru": "Не удалось сохранить: счёт не найден или валюта не совпадает.",
        "en": "Could not save: the account was not found or its currency differs.",
    },

    # ---- Category report ----
    "report_title_current": {
        "uz": "<b>📊 Hisobot: {start} – bugun</b>",
        "ru": "<b>📊 Отчёт: {start} – сегодня</b>",
        "en": "<b>📊 Report: {start} – today</b>",
    },
    "report_title_past": {
        "uz": "<b>📊 Hisobot: {start} – {end}</b>",
        "ru": "<b>📊 Отчёт: {start} – {end}</b>",
        "en": "<b>📊 Report: {start} – {end}</b>",
    },
    "report_totals": {
        "uz": "💰 Daromad: {income}\n💸 Xarajat: {expense}{change}\n⚖️ Balans: {balance}",
        "ru": "💰 Доходы: {income}\n💸 Расходы: {expense}{change}\n⚖️ Баланс: {balance}",
        "en": "💰 Income: {income}\n💸 Expenses: {expense}{change}\n⚖️ Balance: {balance}",
    },
    "report_by_category": {
        "uz": "<i>Kategoriyalar bo'yicha xarajatlar:</i>",
        "ru": "<i>Расходы по категориям:</i>",
        "en": "<i>Expenses by category:</i>",
    },
    "report_new": {"uz": "yangi", "ru": "новое", "en": "new"},
    "report_compare_same_days": {
        "uz": "ℹ️ O'zgarish oldingi davrning shu kunlari bilan ({start} – {end}) solishtirilgan.",
        "ru": "ℹ️ Изменение — по сравнению с теми же днями прошлого периода ({start} – {end}).",
        "en": "ℹ️ Change is compared with the same days of the previous period ({start} – {end}).",
    },
    "report_compare_full": {
        "uz": "ℹ️ O'zgarish oldingi davr bilan ({start} – {end}) solishtirilgan.",
        "ru": "ℹ️ Изменение — по сравнению с прошлым периодом ({start} – {end}).",
        "en": "ℹ️ Change is compared with the previous period ({start} – {end}).",
    },
    "report_combined_head": {
        "uz": "<b>Jami, UZS da</b> (taxminan, kurs: 1 USD = {rate} UZS)",
        "ru": "<b>Всего в UZS</b> (приблизительно, курс: 1 USD = {rate} UZS)",
        "en": "<b>Total in UZS</b> (approximate, rate: 1 USD = {rate} UZS)",
    },
    "report_budgets_head": {"uz": "<b>🎯 Byudjetlar</b>", "ru": "<b>🎯 Бюджеты</b>", "en": "<b>🎯 Budgets</b>"},
    "report_budget_line": {
        "uz": "{category}: {spent} / {limit} — {percent}%\n{bar}",
        "ru": "{category}: {spent} / {limit} — {percent}%\n{bar}",
        "en": "{category}: {spent} / {limit} — {percent}%\n{bar}",
    },
    "report_tap_category": {
        "uz": "Subkategoriyalarni ko'rish uchun kategoriyani bosing.",
        "ru": "Нажмите на категорию, чтобы увидеть подкатегории.",
        "en": "Tap a category to see its subcategories.",
    },
    "report_sub_title": {
        "uz": "<b>📊 {category}</b> · {start} – {end}",
        "ru": "<b>📊 {category}</b> · {start} – {end}",
        "en": "<b>📊 {category}</b> · {start} – {end}",
    },
    "report_sub_empty": {
        "uz": "Bu davrda bu kategoriya bo'yicha xarajat yo'q.",
        "ru": "В этом периоде нет расходов по этой категории.",
        "en": "No expenses in this category in this period.",
    },
    "report_no_sub": {"uz": "subkategoriyasiz", "ru": "без подкатегории", "en": "no subcategory"},
    "report_chart_title": {
        "uz": "Kategoriyalar bo'yicha xarajatlar, {currency}",
        "ru": "Расходы по категориям, {currency}",
        "en": "Expenses by category, {currency}",
    },
    "report_chart_other": {"uz": "Boshqa", "ru": "Другое", "en": "Other"},
    "report_chart_total": {"uz": "Jami: {amount}", "ru": "Итого: {amount}", "en": "Total: {amount}"},

    # ---- Budgets ----
    "btn_budgets": {"uz": "🎯 Byudjetlar", "ru": "🎯 Бюджеты", "en": "🎯 Budgets"},
    "btn_set_budget": {"uz": "✏️ Limitni belgilash", "ru": "✏️ Задать лимит", "en": "✏️ Set limit"},
    "btn_remove_budget": {"uz": "🗑 Limitni o'chirish", "ru": "🗑 Убрать лимит", "en": "🗑 Remove limit"},
    "budgets_title": {
        "uz": "<b>🎯 Byudjetlar</b>\nHar bir xarajat kategoriyasi uchun moliyaviy oy limitini belgilang. "
              "Limitning 80% va 100% ga yetganda ogohlantiraman.",
        "ru": "<b>🎯 Бюджеты</b>\nЗадайте лимит на финансовый месяц для каждой категории расходов. "
              "Я предупрежу, когда он дойдёт до 80% и 100%.",
        "en": "<b>🎯 Budgets</b>\nSet a limit per expense category for the financial month. "
              "I will warn you when it reaches 80% and 100%.",
    },
    "budget_button": {"uz": "{category} — {limit}", "ru": "{category} — {limit}", "en": "{category} — {limit}"},
    "budget_not_set": {"uz": "belgilanmagan", "ru": "не задан", "en": "not set"},
    "budget_details": {
        "uz": "<b>{category}</b>\nLimit: {limit} (oyiga)\nSarflandi: {spent} — {percent}%\n{bar}",
        "ru": "<b>{category}</b>\nЛимит: {limit} (в месяц)\nПотрачено: {spent} — {percent}%\n{bar}",
        "en": "<b>{category}</b>\nLimit: {limit} (per month)\nSpent: {spent} — {percent}%\n{bar}",
    },
    "budget_details_none": {
        "uz": "<b>{category}</b>\nBu kategoriya uchun limit belgilanmagan.",
        "ru": "<b>{category}</b>\nДля этой категории лимит не задан.",
        "en": "<b>{category}</b>\nNo limit is set for this category.",
    },
    "budget_ask_currency": {
        "uz": "«{category}» limiti qaysi valyutada?", "ru": "В какой валюте лимит для «{category}»?",
        "en": "Which currency is the limit for \"{category}\" in?",
    },
    "budget_ask_amount": {
        "uz": "«{category}» uchun oylik limitni kiriting ({currency}). Masalan: 2000000",
        "ru": "Введите месячный лимит для «{category}» ({currency}). Например: 2000000",
        "en": "Enter the monthly limit for \"{category}\" ({currency}). Example: 2000000",
    },
    "budget_saved": {"uz": "Limit saqlandi.", "ru": "Лимит сохранён.", "en": "Limit saved."},
    "budget_removed": {"uz": "Limit o'chirildi.", "ru": "Лимит удалён.", "en": "Limit removed."},

    # ---- Limit alerts ----
    "alert_budget_80": {
        "uz": "⚠️ «{name}» byudjetining {percent}% i ishlatildi: {used} / {limit}.\n{bar}",
        "ru": "⚠️ Бюджет «{name}» использован на {percent}%: {used} / {limit}.\n{bar}",
        "en": "⚠️ Budget \"{name}\" is {percent}% used: {used} / {limit}.\n{bar}",
    },
    "alert_budget_100": {
        "uz": "🚨 «{name}» byudjeti tugadi: {used} / {limit} ({percent}%).\n{bar}",
        "ru": "🚨 Бюджет «{name}» исчерпан: {used} / {limit} ({percent}%).\n{bar}",
        "en": "🚨 Budget \"{name}\" is used up: {used} / {limit} ({percent}%).\n{bar}",
    },
    "alert_credit_80": {
        "uz": "⚠️ «{name}» kredit limitining {percent}% i ishlatildi: qarz {used} / {limit}.\n{bar}",
        "ru": "⚠️ Кредитный лимит «{name}» использован на {percent}%: долг {used} / {limit}.\n{bar}",
        "en": "⚠️ Credit limit of \"{name}\" is {percent}% used: debt {used} / {limit}.\n{bar}",
    },
    "alert_credit_100": {
        "uz": "🚨 «{name}» kredit limiti to'ldi: qarz {used} / {limit} ({percent}%).\n{bar}",
        "ru": "🚨 Кредитный лимит «{name}» исчерпан: долг {used} / {limit} ({percent}%).\n{bar}",
        "en": "🚨 Credit limit of \"{name}\" is reached: debt {used} / {limit} ({percent}%).\n{bar}",
    },

    # ---- Ask AI ----
    "btn_advice_now": {"uz": "💡 Maslahat olish", "ru": "💡 Получить совет", "en": "💡 Get advice now"},
    "ask_thinking": {"uz": "🤔 O'ylayapman...", "ru": "🤔 Думаю...", "en": "🤔 Thinking..."},
    "ask_error_refused": {
        "uz": "AI bu savolga javob bermadi. Savolni boshqacha yozib ko'ring.",
        "ru": "AI не стал отвечать на этот вопрос. Попробуйте сформулировать иначе.",
        "en": "The AI declined to answer this. Try rephrasing the question.",
    },
    "ask_error_bad_input": {
        "uz": "AI so'rovni qabul qilmadi. Qayta urinib ko'ring yoki /start bilan yangi suhbat boshlang.",
        "ru": "AI не принял запрос. Попробуйте ещё раз или начните новый диалог командой /start.",
        "en": "The AI rejected the request. Try again or start a new conversation with /start.",
    },

    # ---- AI advice ----
    "btn_ai_advice": {"uz": "🤖 AI maslahatlari", "ru": "🤖 AI-советы", "en": "🤖 AI advice"},
    "btn_advice_weekly": {"uz": "Haftalik xulosa", "ru": "Недельная сводка", "en": "Weekly summary"},
    "btn_advice_monthly": {"uz": "Oylik xulosa", "ru": "Месячная сводка", "en": "Monthly review"},
    "advice_on": {"uz": "yoqilgan", "ru": "включена", "en": "on"},
    "advice_off": {"uz": "o'chirilgan", "ru": "выключена", "en": "off"},
    "advice_settings": {
        "uz": "<b>🤖 AI maslahatlari</b>\n\n"
              "📅 Haftalik xulosa — har dushanba 09:00 da: o'tgan 7 kun, oldingi hafta bilan solishtirish, "
              "tejash bo'yicha maslahatlar. Holati: {weekly}\n"
              "📆 Oylik xulosa — yangi moliyaviy oy boshlanadigan kuni ({salary_day}-sana) 09:00 da: butun davr, "
              "byudjetlar, kredit kartalar. Holati: {monthly}\n\n"
              "Davrda amallar bo'lmasa, xulosa yuborilmaydi. Hisob-kitob xulosalari AI xizmatiga yuboriladi.",
        "ru": "<b>🤖 AI-советы</b>\n\n"
              "📅 Недельная сводка — каждый понедельник в 09:00: последние 7 дней, сравнение с прошлой неделей, "
              "советы по экономии. Сейчас: {weekly}\n"
              "📆 Месячная сводка — в день начала нового финансового месяца ({salary_day}-е число) в 09:00: весь "
              "период, бюджеты, кредитные карты. Сейчас: {monthly}\n\n"
              "Если операций за период не было, сводка не отправляется. Сводки по вашим данным отправляются в "
              "AI-сервис.",
        "en": "<b>🤖 AI advice</b>\n\n"
              "📅 Weekly summary — every Monday at 09:00: the last 7 days compared with the week before, plus "
              "saving tips. Now: {weekly}\n"
              "📆 Monthly review — at 09:00 on the day your new financial month starts (day {salary_day}): the "
              "whole period, budgets and credit cards. Now: {monthly}\n\n"
              "Nothing is sent for a period without operations. Summaries of your data are sent to the AI service.",
    },
    "advice_preparing": {
        "uz": "⏳ Maslahat tayyorlanmoqda...", "ru": "⏳ Готовлю совет...", "en": "⏳ Preparing advice...",
    },
    "advice_no_data": {
        "uz": "Maslahat uchun ma'lumot yetarli emas: bu davrda daromad yoki xarajat yo'q.",
        "ru": "Пока недостаточно данных для совета: в этом периоде нет доходов и расходов.",
        "en": "Not enough data for advice yet: no income or expenses in this period.",
    },
    "advice_title_weekly": {
        "uz": "📅 <b>Haftalik xulosa</b> · {start} – {end}", "ru": "📅 <b>Недельная сводка</b> · {start} – {end}",
        "en": "📅 <b>Weekly summary</b> · {start} – {end}",
    },
    "advice_title_monthly": {
        "uz": "📆 <b>Oylik xulosa</b> · {start} – {end}", "ru": "📆 <b>Месячная сводка</b> · {start} – {end}",
        "en": "📆 <b>Monthly review</b> · {start} – {end}",
    },
    "advice_title_now": {
        "uz": "💡 <b>AI maslahati</b> · {start} – {end}", "ru": "💡 <b>Совет AI</b> · {start} – {end}",
        "en": "💡 <b>AI advice</b> · {start} – {end}",
    },

    # ---- Report cards (receipt-style images, utils/cards.py; plain text, escaped by the template) ----
    "card_title_weekly": {"uz": "Haftalik chek", "ru": "Недельный чек", "en": "Weekly receipt"},
    "card_title_monthly": {"uz": "Oylik chek", "ru": "Месячный чек", "en": "Monthly receipt"},
    "card_title_report": {"uz": "Hisobot", "ru": "Отчёт", "en": "Report"},
    "card_expenses_one": {"uz": "{n} ta xarajat", "ru": "{n} трата", "en": "{n} expense"},
    "card_expenses_few": {"uz": "{n} ta xarajat", "ru": "{n} траты", "en": "{n} expenses"},
    "card_expenses_many": {"uz": "{n} ta xarajat", "ru": "{n} трат", "en": "{n} expenses"},
    "card_days_one": {"uz": "{n} kun", "ru": "{n} день", "en": "{n} day"},
    "card_days_few": {"uz": "{n} kun", "ru": "{n} дня", "en": "{n} days"},
    "card_days_many": {"uz": "{n} kun", "ru": "{n} дней", "en": "{n} days"},
    "card_week_no": {"uz": "№ {week}", "ru": "№ {week}", "en": "№ {week}"},
    "card_categories": {"uz": "Kategoriyalar", "ru": "Категории", "en": "Categories"},
    "card_currencies": {"uz": "{n} valyuta", "ru": "{n} валюты", "en": "{n} currencies"},
    "card_more": {"uz": "Koʻproq", "ru": "Больше", "en": "More"},
    "card_less": {"uz": "Kamroq", "ru": "Меньше", "en": "Less"},
    "card_same": {"uz": "Oʻshancha", "ru": "Столько же", "en": "Same"},
    "card_separate": {"uz": "Alohida", "ru": "Раздельно", "en": "Separate"},
    "card_total": {"uz": "Jami", "ru": "Итого", "en": "Total"},
    "card_total_in": {"uz": "Jami, {currency}", "ru": "Итого, {currency}", "en": "Total, {currency}"},
    "card_currency_UZS": {"uz": "soʻm", "ru": "сум", "en": "UZS"},
    "card_currency_USD": {"uz": "USD", "ru": "USD", "en": "USD"},
    "card_section_UZS": {"uz": "Soʻmda", "ru": "В сумах", "en": "In UZS"},
    "card_section_USD": {"uz": "Dollarda", "ru": "В долларах", "en": "In USD"},
    "card_prev_week": {"uz": "Oʻtgan hafta", "ru": "Прошлая неделя", "en": "Last week"},
    "card_prev_month": {"uz": "Oʻtgan oy", "ru": "Прошлый месяц", "en": "Last month"},
    "card_prev_period": {"uz": "Oldingi davr", "ru": "Прошлый период", "en": "Previous period"},
    "card_prev_same_days": {
        "uz": "Oldingi davr, shu {days}", "ru": "Прошлый период, те же {days}", "en": "Previous period, same {days}",
    },
    "card_by_day": {"uz": "KUNLAR · {unit}", "ru": "ДНИ · {unit}", "en": "DAYS · {unit}"},
    "card_by_week": {"uz": "HAFTALAR · {unit}", "ru": "НЕДЕЛИ · {unit}", "en": "WEEKS · {unit}"},
    "card_unit_UZS": {"uz": "ming soʻm", "ru": "тыс. сум", "en": "thousand UZS"},
    "card_unit_USD": {"uz": "USD", "ru": "USD", "en": "USD"},
    "card_weekdays": {"uz": "Du Se Ch Pa Ju Sh Ya", "ru": "Пн Вт Ср Чт Пт Сб Вс", "en": "Mo Tu We Th Fr Sa Su"},
    "card_weekdays_long": {
        "uz": "Dush Sesh Chor Pay Juma Shan Yak",
        "ru": "Понедельник Вторник Среда Четверг Пятница Суббота Воскресенье",
        "en": "Monday Tuesday Wednesday Thursday Friday Saturday Sunday",
    },
    "card_week_n": {"uz": "{n}-hafta", "ru": "{n}-я нед.", "en": "Week {n}"},
    "card_biggest": {"uz": "Eng katta xarajat", "ru": "Самая крупная трата", "en": "Biggest expense"},
    "card_biggest_list": {"uz": "Eng katta xarajatlar", "ru": "Самые крупные траты", "en": "Biggest expenses"},
    "card_budget_note": {
        "uz": "* {category} byudjeti: {percent}% ishlatildi",
        "ru": "* Бюджет «{category}»: израсходовано {percent}%",
        "en": "* {category} budget: {percent}% used",
    },
    "card_budgets": {"uz": "Byudjetlar", "ru": "Бюджеты", "en": "Budgets"},
    "card_budgets_over": {"uz": "! {n} tasi oshdi", "ru": "! превышено: {n}", "en": "! {n} over"},
    "card_over_budget": {"uz": "Byudjetdan oshgan", "ru": "Сверх бюджета", "en": "Over budget"},
    "card_over_count": {"uz": "! {n} ta", "ru": "! {n}", "en": "! {n}"},
    "card_income": {"uz": "Daromad", "ru": "Доходы", "en": "Income"},
    "card_expense": {"uz": "Xarajat", "ru": "Расходы", "en": "Expenses"},
    "card_balance": {"uz": "Qoldiq", "ru": "Остаток", "en": "Balance"},
    "card_prev_balance": {
        "uz": "Oʻtgan oy qoldigʻi: {amount}", "ru": "Остаток прошлого месяца: {amount}",
        "en": "Last month's balance: {amount}",
    },
    "card_payment": {"uz": "Toʻlov usuli", "ru": "Способ оплаты", "en": "Payment method"},
    "card_pay_cash": {"uz": "Naqd", "ru": "Наличные", "en": "Cash"},
    "card_pay_debit": {"uz": "Debet karta", "ru": "Дебетовая карта", "en": "Debit card"},
    "card_pay_credit": {"uz": "Kredit karta", "ru": "Кредитная карта", "en": "Credit card"},
    "card_credit_limit": {"uz": "Kredit limiti", "ru": "Кредитный лимит", "en": "Credit limit"},
    "card_thanks": {"uz": "RAHMAT!", "ru": "СПАСИБО!", "en": "THANK YOU!"},
    "card_legend": {"uz": "▲ koʻp · ▼ kam", "ru": "▲ больше · ▼ меньше", "en": "▲ more · ▼ less"},
    "card_mixed_note": {
        "uz": "* Valyutalar alohida hisoblangan, kurs boʻyicha qoʻshilmagan.",
        "ru": "* Валюты посчитаны отдельно, без пересчёта по курсу.",
        "en": "* Currencies are counted separately, not converted at a rate.",
    },
    "card_empty_stamp": {"uz": "Xarajat yoʻq", "ru": "Расходов нет", "en": "No expenses"},
    "card_empty_when_weekly": {"uz": "Bu hafta", "ru": "За неделю", "en": "This week"},
    "card_empty_when_monthly": {"uz": "Bu oy", "ru": "За месяц", "en": "This month"},
    "card_empty_when_report": {"uz": "Bu davrda", "ru": "За период", "en": "This period"},
    "card_empty_text_weekly": {
        "uz": "Hamyoningiz bu hafta dam oldi.", "ru": "Кошелёк отдыхал всю неделю.",
        "en": "Your wallet took the week off.",
    },
    "card_empty_text_monthly": {
        "uz": "Hamyoningiz bu oy dam oldi.", "ru": "Кошелёк отдыхал весь месяц.",
        "en": "Your wallet took the month off.",
    },
    "card_empty_text_report": {
        "uz": "Bu davrda xarajat yozilmagan.", "ru": "В этом периоде расходов нет.",
        "en": "No expenses in this period.",
    },
    "card_empty_hint": {
        "uz": "Xarajat qoʻshish uchun yozing: «taksi 25\u202f000»",
        "ru": "Чтобы добавить расход, напишите: «такси 25\u202f000»",
        "en": "To add an expense, write: “taxi 25\u202f000”",
    },
}


# ---- Mini App (webapp/): plain text, rendered with textContent; "{name}"-style placeholders are filled in JS ----
WEBAPP_TEXTS = {
    "title_main": {"uz": "KARTALARIM", "ru": "МОИ КАРТЫ", "en": "MY CARDS"},
    "total_balance": {"uz": "JAMI BALANS", "ru": "ОБЩИЙ БАЛАНС", "en": "TOTAL BALANCE"},
    "accounts_count": {"uz": "{n} ta hisob", "ru": "счетов: {n}", "en": "accounts: {n}"},
    "section_accounts": {"uz": "HISOBLAR", "ru": "СЧЕТА", "en": "ACCOUNTS"},
    "col_balance": {"uz": "balans", "ru": "баланс", "en": "balance"},
    "add_card": {"uz": "KARTA QO'SHISH", "ru": "ДОБАВИТЬ КАРТУ", "en": "ADD CARD"},
    "no_accounts": {"uz": "Hali hisob yo'q", "ru": "Счетов пока нет", "en": "No accounts yet"},
    "limit_line": {"uz": "limit {amount}", "ru": "лимит {amount}", "en": "limit {amount}"},
    "sum": {"uz": "so'm", "ru": "сум", "en": "UZS"},
    "tag_cash": {"uz": "NAQD", "ru": "НАЛ", "en": "CASH"},
    "tag_credit": {"uz": "KREDIT", "ru": "КРЕДИТ", "en": "CREDIT"},
    "tag_card": {"uz": "KARTA", "ru": "КАРТА", "en": "CARD"},
    "title_new": {"uz": "YANGI KARTA", "ru": "НОВАЯ КАРТА", "en": "NEW CARD"},
    "title_edit": {"uz": "TAHRIRLASH", "ru": "ИЗМЕНИТЬ КАРТУ", "en": "EDIT CARD"},
    "lbl_type": {"uz": "TURI", "ru": "ТИП", "en": "TYPE"},
    "lbl_name": {"uz": "NOMI / BANK", "ru": "НАЗВАНИЕ / БАНК", "en": "NAME / BANK"},
    "lbl_last4": {"uz": "OXIRGI 4 RAQAM", "ru": "ПОСЛЕДНИЕ 4 ЦИФРЫ", "en": "LAST 4 DIGITS"},
    "lbl_currency": {"uz": "VALYUTA", "ru": "ВАЛЮТА", "en": "CURRENCY"},
    "lbl_balance": {"uz": "HOZIRGI BALANS", "ru": "ТЕКУЩИЙ БАЛАНС", "en": "CURRENT BALANCE"},
    "lbl_debt": {"uz": "HOZIRGI QARZ", "ru": "ТЕКУЩИЙ ДОЛГ", "en": "CURRENT DEBT"},
    "lbl_limit": {"uz": "KREDIT LIMITI", "ru": "КРЕДИТНЫЙ ЛИМИТ", "en": "CREDIT LIMIT"},
    "credit_title": {"uz": "Kredit karta", "ru": "Кредитная карта", "en": "Credit card"},
    "credit_hint": {
        "uz": "Limit va qarz alohida ko'rsatiladi", "ru": "Лимит и долг показываются отдельно",
        "en": "Limit and debt are shown separately",
    },
    "note_last4": {
        "uz": "Karta raqamining faqat oxirgi 4 ta raqami saqlanadi: bot SMS'dagi *{last4} orqali kartani o'zi taniydi.",
        "ru": "Хранятся только последние 4 цифры номера карты: бот сам узнает карту по *{last4} в SMS.",
        "en": "Only the last 4 digits of the card number are stored: the bot recognizes the card by *{last4} "
              "in a bank SMS.",
    },
    "save": {"uz": "SAQLASH", "ru": "СОХРАНИТЬ", "en": "SAVE"},
    "back": {"uz": "Orqaga", "ru": "Назад", "en": "Back"},
    "balance": {"uz": "BALANS", "ru": "БАЛАНС", "en": "BALANCE"},
    "debt": {"uz": "QARZ", "ru": "ДОЛГ", "en": "DEBT"},
    "available": {"uz": "mavjud {amount}", "ru": "доступно {amount}", "en": "available {amount}"},
    "month_expense": {"uz": "BU OY CHIQIM", "ru": "РАСХОД ЗА МЕСЯЦ", "en": "SPENT THIS MONTH"},
    "month_income": {"uz": "BU OY KIRIM", "ru": "ДОХОД ЗА МЕСЯЦ", "en": "INCOME THIS MONTH"},
    "recent_ops": {"uz": "OXIRGI AMALLAR", "ru": "ПОСЛЕДНИЕ ОПЕРАЦИИ", "en": "RECENT OPERATIONS"},
    "no_ops": {"uz": "Hali amallar yo'q", "ru": "Операций пока нет", "en": "No operations yet"},
    "op_income": {"uz": "Kirim", "ru": "Доход", "en": "Income"},
    "op_transfer": {"uz": "O'tkazma", "ru": "Перевод", "en": "Transfer"},
    "op_expense": {"uz": "Xarajat", "ru": "Расход", "en": "Expense"},
    "edit": {"uz": "TAHRIRLASH", "ru": "ИЗМЕНИТЬ", "en": "EDIT"},
    "delete": {"uz": "Kartani o'chirish", "ru": "Удалить карту", "en": "Delete card"},
    "confirm_delete": {
        "uz": "«{name}» o'chirilsinmi?", "ru": "Удалить «{name}»?", "en": "Delete “{name}”?",
    },
    "confirm_archive": {
        "uz": "«{name}» hisobida amallar bor: u arxivlanadi (ro'yxatdan yashiriladi, tarix saqlanadi). Davom etilsinmi?",
        "ru": "У «{name}» есть операции: счёт будет архивирован (скрыт из списка, история сохранится). Продолжить?",
        "en": "“{name}” has operations: it will be archived (hidden from the list, history kept). Continue?",
    },
    "deleted": {"uz": "Karta o'chirildi", "ru": "Карта удалена", "en": "Card deleted"},
    "archived": {"uz": "Karta arxivlandi", "ru": "Карта архивирована", "en": "Card archived"},
    "saved": {"uz": "Saqlandi", "ru": "Сохранено", "en": "Saved"},
    "loading": {"uz": "Yuklanmoqda…", "ru": "Загрузка…", "en": "Loading…"},
    "err_name": {"uz": "Nomini yozing (40 belgigacha)", "ru": "Введите название (до 40 символов)",
                 "en": "Enter a name (up to 40 characters)"},
    "err_last4": {"uz": "Kartaning oxirgi 4 raqamini yozing", "ru": "Введите последние 4 цифры карты",
                  "en": "Enter the last 4 digits of the card"},
    "err_last4_taken": {"uz": "Bu 4 raqamli boshqa karta bor", "ru": "Карта с этими 4 цифрами уже есть",
                        "en": "Another card already has these 4 digits"},
    "err_amount": {"uz": "Summa noto'g'ri", "ru": "Неверная сумма", "en": "Invalid amount"},
    "err_currency_locked": {
        "uz": "Amallari bor hisobning valyutasini o'zgartirib bo'lmaydi",
        "ru": "Нельзя сменить валюту счёта, у которого есть операции",
        "en": "The currency of an account with operations cannot change",
    },
    "err_not_found": {"uz": "Hisob topilmadi", "ru": "Счёт не найден", "en": "Account not found"},
    "err_auth": {
        "uz": "Ilovani bot ichidagi tugma orqali oching", "ru": "Откройте приложение кнопкой в боте",
        "en": "Open the app from the button in the bot",
    },
    "err_forbidden": {"uz": "Bu shaxsiy bot. Kirish yopiq.", "ru": "Это личный бот. Доступ закрыт.",
                      "en": "This is a private bot. Access is restricted."},
    "err_generic": {"uz": "Xatolik. Qayta urinib ko'ring", "ru": "Ошибка. Попробуйте ещё раз",
                    "en": "Something went wrong. Try again"},
}


def webapp_texts(lang: Optional[str]) -> dict:
    """All Mini App texts in one language (missing ones fall back to English)."""
    lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
    return {key: variants.get(lang) or variants["en"] for key, variants in WEBAPP_TEXTS.items()}
