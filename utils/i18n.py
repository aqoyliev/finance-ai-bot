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
              "«taksi 25000 naqd». Chek rasmi yoki bank SMS'ini ham yuborishingiz mumkin — bot darhol saqlaydi. "
              "Savol ham bering: «bu oy taksiga qancha ketdi?»\n\n"
              "Qolgan hammasi — balans, hisobot, tarix, kartalar va sozlamalar — 📱 ilovada.",
        "ru": "<b>ФИНАНСОВЫЙ БОТ</b>\n\nПросто напишите или наговорите расход или доход, например: "
              "«такси 25000 наличными». Можно прислать фото чека или банковское SMS — бот сразу сохранит. "
              "Можно и спросить: «сколько ушло на такси в этом месяце?»\n\n"
              "Всё остальное — баланс, отчёт, история, карты и настройки — в 📱 приложении.",
        "en": "<b>FINANCE BOT</b>\n\nJust type or say an expense or income, e.g. \"taxi 25000 cash\". "
              "You can also send a receipt photo or a bank SMS — the bot saves it right away. "
              "Or ask a question: \"how much did I spend on taxi this month?\"\n\n"
              "Everything else — balance, report, history, cards and settings — is in the 📱 app.",
    },
    "bot_started": {"uz": "Bot ishga tushdi", "ru": "Бот запущен", "en": "Bot has started"},
    "cmd_start": {"uz": "Boshlash", "ru": "Начало", "en": "Start"},
    "cmd_help": {"uz": "Yordam", "ru": "Помощь", "en": "Help"},
    "language_changed": {
        "uz": "Til o'zgartirildi: o'zbekcha.",
        "ru": "Язык изменён: русский.",
        "en": "Language changed: English.",
    },
    "help": {
        "uz": "<b>🤖 Amal qo'shish</b>\n"
              "Shunchaki yozing yoki ayting: «taksi 25000 naqd», «kofe 18 ming», «maosh 12m hamkorbankka». "
              "Chek rasmi, PDF yoki bank SMS'ini ham yuborish mumkin. Bot amalni darhol saqlaydi: to'lov usuli "
              "aniq bo'lmasa, faqat shuni so'raydi; kategoriya aniq bo'lmasa, «Boshqa» ga yoziladi. "
              "Ovozli xabar 2 daqiqagacha bo'lishi kerak va faqat Google Gemini bilan ishlaydi. "
              "Rasm, ovoz va matn tahlil uchun AI xizmatiga (Google Gemini yoki Anthropic Claude) yuboriladi.\n\n"
              "<b>💬 Savollar va maslahatlar</b>\n"
              "Savolni shunchaki yozing (masalan «bu oy taksiga qancha ketdi?»). Har dushanba 09:00 da haftalik "
              "xulosa, yangi moliyaviy oy boshlanganda 09:00 da oylik xulosa keladi. Limitning yoki kredit karta "
              "limitining 80% va 100% ga yetganda bot xabar yuboradi.\n\n"
              "<b>📱 Ilova</b>\n"
              "Asosiy: balans, oy xarajati va kirimi, limitlar, kartalar. ➕ — amalni qo'lda kiritish (o'tkazma ham). "
              "Tarix: qidirish, tahrirlash va o'chirish. Hisobot: hafta / oy / yil, kategoriyalar va AI maslahat. "
              "Sozlamalar: kartalar, maosh kuni, dollar kursi, oylik limitlar, AI maslahatlar va til.\n\n"
              "/start — boshlash · /help — yordam",
        "ru": "<b>🤖 Добавить операцию</b>\n"
              "Просто напишите или наговорите: «такси 25000 наличными», «кофе 18 тысяч», «зарплата 12м на "
              "hamkorbank». Можно отправить фото или PDF чека или банковское SMS. Бот сразу сохраняет операцию: "
              "если непонятен способ оплаты, спросит только его; если непонятна категория, запишет в «Прочее». "
              "Голосовые — до 2 минут, работают только с Google Gemini. "
              "Фото, голос и текст отправляются на анализ в AI-сервис (Google Gemini или Anthropic Claude).\n\n"
              "<b>💬 Вопросы и советы</b>\n"
              "Просто напишите вопрос (например «сколько я потратил на такси в этом месяце?»). Каждый понедельник "
              "в 09:00 приходит недельная сводка, а в 09:00 в первый день нового финансового месяца — месячная. "
              "Когда бюджет или кредитный лимит дойдёт до 80% и 100%, бот напишет.\n\n"
              "<b>📱 Приложение</b>\n"
              "Главная: баланс, расходы и доходы месяца, лимиты, карты. ➕ — ввести операцию вручную (и перевод). "
              "История: поиск, изменение и удаление. Отчёт: неделя / месяц / год, категории и совет AI. "
              "Настройки: карты, день зарплаты, курс доллара, месячные лимиты, AI-советы и язык.\n\n"
              "/start — начало · /help — помощь",
        "en": "<b>🤖 Adding operations</b>\n"
              "Just type or say it: \"taxi 25000 cash\", \"coffee 18k\", \"got salary 12m to hamkorbank\". "
              "You can also send a receipt photo or PDF or a bank SMS. The bot saves the operation right away: if "
              "the payment method is unclear it asks only for that; an unclear category goes to \"Other\". "
              "Voice messages can be up to 2 minutes and work with Google Gemini only. "
              "Photos, voice and text are sent to the AI service (Google Gemini or Anthropic Claude) for "
              "analysis.\n\n"
              "<b>💬 Questions and advice</b>\n"
              "Just type a question (e.g. \"how much did I spend on taxi this month?\"). A weekly summary arrives "
              "every Monday at 09:00 and a monthly review at 09:00 on the first day of a new financial month. The "
              "bot messages you when a budget or a credit card limit reaches 80% and 100%.\n\n"
              "<b>📱 The app</b>\n"
              "Home: balance, the month's expenses and income, limits, cards. ➕ adds an operation by hand (also a "
              "transfer). History: search, edit and delete. Report: week / month / year, categories and AI advice. "
              "Settings: cards, salary day, USD rate, monthly limits, AI advice and language.\n\n"
              "/start — start · /help — help",
    },
    "moved_to_app": {
        "uz": "Amalni yozing yoki ayting (masalan «taksi 25000 naqd»), chek yoki SMS yuboring. Balans, hisobot, "
              "tarix va sozlamalar endi 📱 ilovada.",
        "ru": "Напишите или наговорите операцию (например «такси 25000 наличными»), пришлите чек или SMS. Баланс, "
              "отчёт, история и настройки теперь в 📱 приложении.",
        "en": "Type or say an operation (e.g. \"taxi 25000 cash\"), or send a receipt or SMS. Balance, report, "
              "history and settings are in the 📱 app now.",
    },
    "btn_open_app": {"uz": "📱 Ilovani ochish", "ru": "📱 Открыть приложение", "en": "📱 Open the app"},
    "open_app_hint": {"uz": "📱 Ilova:", "ru": "📱 Приложение:", "en": "📱 The app:"},
    "btn_advice_settings": {"uz": "⚙️ Maslahat sozlamalari", "ru": "⚙️ Настройки советов",
                            "en": "⚙️ Advice settings"},
    "session_lost": {
        "uz": "Sessiya tugadi. Qaytadan boshlang: /start",
        "ru": "Сессия истекла. Начните заново: /start",
        "en": "Session expired. Start again: /start",
    },

    # ---- Buttons ----
    # Labels of the removed reply keyboard: still recognized, answered with a hint to the Mini App
    "old_kb_report": {"uz": "📊 Hisobot", "ru": "📊 Отчёт", "en": "📊 Report"},
    "old_kb_balance": {"uz": "💳 Balans", "ru": "💳 Баланс", "en": "💳 Balance"},
    "old_kb_settings": {"uz": "⚙️ Sozlamalar", "ru": "⚙️ Настройки", "en": "⚙️ Settings"},
    "menu_miniapp": {"uz": "Ilova", "ru": "Приложение", "en": "App"},

    # ---- Access (users managed in the Mini App) ----
    "visitor_knocks": {
        "uz": "👤 {name} ({username}) botga kirmoqchi",
        "ru": "👤 {name} ({username}) хочет пользоваться ботом",
        "en": "👤 {name} ({username}) wants to use the bot",
    },
    "no_username": {"uz": "username yo'q", "ru": "без username", "en": "no username"},
    "btn_grant": {"uz": "✅ Ruxsat berish", "ru": "✅ Дать доступ", "en": "✅ Grant access"},
    "grant_done": {"uz": "✅ {name} — ruxsat berildi", "ru": "✅ {name} — доступ выдан", "en": "✅ {name} — access granted"},
    "grant_already": {"uz": "Bu odamda allaqachon ruxsat bor", "ru": "У этого человека уже есть доступ",
                      "en": "This person already has access"},
    "grant_not_manager": {"uz": "Faqat admin ruxsat bera oladi", "ru": "Выдавать доступ может только админ",
                          "en": "Only an admin can grant access"},
    "access_granted": {
        "uz": "✅ Sizga botdan foydalanishga ruxsat berildi! Boshlash uchun /start bosing.",
        "ru": "✅ Вам открыли доступ к боту! Чтобы начать, нажмите /start.",
        "en": "✅ You now have access to the bot! Tap /start to begin.",
    },
    "picker_prompt": {
        "uz": "Ruxsat beriladigan odamni kontaktlardan tanlang 👇",
        "ru": "Выберите в контактах, кому дать доступ 👇",
        "en": "Pick the person to give access to from your contacts 👇",
    },
    "picker_btn": {"uz": "👤 Tanlash", "ru": "👤 Выбрать", "en": "👤 Choose"},
    "picker_cancel": {"uz": "❌ Bekor qilish", "ru": "❌ Отмена", "en": "❌ Cancel"},
    "picker_cancelled": {"uz": "Bekor qilindi", "ru": "Отменено", "en": "Cancelled"},

    # ---- Saved operations ----
    "no_accounts_in_currency": {
        "uz": "Sizda hali {currency} hisoblari yo'q.",
        "ru": "У вас пока нет счетов в {currency}.",
        "en": "You have no {currency} accounts yet.",
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

    # ---- AI input (receipts, voice, free text, bank SMS) ----
    "ai_not_configured": {
        "uz": "🤖 AI kiritish sozlanmagan ({env_key} yo'q). Amalni 📱 ilovada ➕ orqali qo'lda kiriting.",
        "ru": "🤖 AI-ввод не настроен (нет {env_key}). Введите операцию вручную в 📱 приложении через ➕.",
        "en": "🤖 AI input is not configured (no {env_key}). Add the operation by hand in the 📱 app with ➕.",
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
        "uz": "🚦 AI so'rovlar limiti tugadi. Keyinroq urinib ko'ring yoki 📱 ilovada ➕ orqali qo'lda kiriting.",
        "ru": "🚦 Исчерпан лимит запросов к AI. Попробуйте позже или введите вручную в 📱 приложении (➕).",
        "en": "🚦 The AI request quota is exhausted. Try later or add it by hand in the 📱 app (➕).",
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
        "uz": "💳 Tugmalardan birini tanlang yoki hisob nomini yozing.",
        "ru": "💳 Выберите одну из кнопок или напишите название счёта.",
        "en": "💳 Pick one of the buttons or type the account name.",
    },
    "ai_new_card_hint": {
        "uz": "Yangi karta bo'lsa: ➕ tugmasi bilan ilovada qo'shing, keyin uning nomini shu yerga yozing.",
        "ru": "Новая карта? Добавьте её в приложении кнопкой ➕, затем напишите её название здесь.",
        "en": "A new card? Add it in the app with the ➕ button, then type its name here.",
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
        "uz": "🤖 O'tkazma qaysi hisobga ekanini tushunmadim. Uni 📱 ilovada ➕ → O'tkazma orqali kiriting.",
        "ru": "🤖 Не понял, на какой счёт перевод. Введите его в 📱 приложении: ➕ → Перевод.",
        "en": "🤖 I could not tell which account the transfer goes to. Add it in the 📱 app: ➕ → Transfer.",
    },
    "ai_already_saved": {
        "uz": "⏭ Bu xabar yoki fayl allaqachon saqlangan — qayta yozilmadi.",
        "ru": "⏭ Это сообщение или файл уже сохранены — повторно не записано.",
        "en": "⏭ This message or file was already saved — not recorded again.",
    },
    "ai_duplicate": {
        "uz": "⚠️ Yaqinda shu hisobdan xuddi shunday summa yozilgan. Ikki marta yozilgan bo'lsa, o'chiring: "
              "📱 ilova → Tarix.",
        "ru": "⚠️ Недавно с этого счёта уже записана такая же сумма. Если это дубль, удалите его: "
              "📱 приложение → История.",
        "en": "⚠️ The same amount on this account was recorded a few minutes ago. If it is a duplicate, delete "
              "it: 📱 app → History.",
    },
    "ai_save_failed": {
        "uz": "Saqlab bo'lmadi: hisob topilmadi yoki valyuta mos emas.",
        "ru": "Не удалось сохранить: счёт не найден или валюта не совпадает.",
        "en": "Could not save: the account was not found or its currency differs.",
    },

    # ---- Report chart (fallback of the receipt cards) ----
    "report_new": {"uz": "yangi", "ru": "новое", "en": "new"},
    "report_chart_title": {
        "uz": "Kategoriyalar bo'yicha xarajatlar, {currency}",
        "ru": "Расходы по категориям, {currency}",
        "en": "Expenses by category, {currency}",
    },
    "report_chart_other": {"uz": "Boshqa", "ru": "Другое", "en": "Other"},
    "report_chart_total": {"uz": "Jami: {amount}", "ru": "Итого: {amount}", "en": "Total: {amount}"},

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
    "advice_title_weekly": {
        "uz": "📅 <b>Haftalik xulosa</b> · {start} – {end}", "ru": "📅 <b>Недельная сводка</b> · {start} – {end}",
        "en": "📅 <b>Weekly summary</b> · {start} – {end}",
    },
    "advice_title_monthly": {
        "uz": "📆 <b>Oylik xulosa</b> · {start} – {end}", "ru": "📆 <b>Месячная сводка</b> · {start} – {end}",
        "en": "📆 <b>Monthly review</b> · {start} – {end}",
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

    # ---- Tabs, Home ----
    "app_title": {"uz": "Moliya", "ru": "Финансы", "en": "Finance"},
    "tab_home": {"uz": "ASOSIY", "ru": "ГЛАВНАЯ", "en": "HOME"},
    "tab_history": {"uz": "TARIX", "ru": "ИСТОРИЯ", "en": "HISTORY"},
    "tab_report": {"uz": "HISOBOT", "ru": "ОТЧЁТ", "en": "REPORT"},
    "tab_settings": {"uz": "SOZLAMA", "ru": "НАСТРОЙКИ", "en": "SETTINGS"},
    "tabs_label": {"uz": "Bo'limlar", "ru": "Разделы", "en": "Sections"},
    "add_op": {"uz": "Amal qo'shish", "ru": "Добавить операцию", "en": "Add an operation"},
    "months": {
        "uz": "YANVAR,FEVRAL,MART,APREL,MAY,IYUN,IYUL,AVGUST,SENTABR,OKTABR,NOYABR,DEKABR",
        "ru": "ЯНВАРЬ,ФЕВРАЛЬ,МАРТ,АПРЕЛЬ,МАЙ,ИЮНЬ,ИЮЛЬ,АВГУСТ,СЕНТЯБРЬ,ОКТЯБРЬ,НОЯБРЬ,ДЕКАБРЬ",
        "en": "JANUARY,FEBRUARY,MARCH,APRIL,MAY,JUNE,JULY,AUGUST,SEPTEMBER,OCTOBER,NOVEMBER,DECEMBER",
    },
    "rate_line": {"uz": "1 USD = {rate} so'm", "ru": "1 USD = {rate} сум", "en": "1 USD = {rate} UZS"},
    "rate_src_cbu": {"uz": "Markaziy bank", "ru": "Центробанк", "en": "Central Bank"},
    "rate_src_market": {"uz": "Bozor kursi", "ru": "Рыночный курс", "en": "Market rate"},
    "rate_src_manual": {"uz": "Qo'lda", "ru": "Вручную", "en": "Manual"},
    "rate_none": {"uz": "Dollar kursi noma'lum", "ru": "Курс доллара неизвестен", "en": "USD rate unknown"},
    "cap_expense": {"uz": "CHIQIM", "ru": "РАСХОД", "en": "EXPENSES"},
    "cap_income": {"uz": "KIRIM", "ru": "ДОХОД", "en": "INCOME"},
    "limit_title": {"uz": "Oylik limit", "ru": "Месячный лимит", "en": "Monthly limit"},
    "limit_left": {"uz": "{percent}% · {amount} qoldi", "ru": "{percent}% · осталось {amount}",
                   "en": "{percent}% · {amount} left"},
    "limit_over": {"uz": "{percent}% · limitdan oshdi", "ru": "{percent}% · лимит превышен",
                   "en": "{percent}% · over the limit"},
    "sec_cards": {"uz": "KARTALAR", "ru": "КАРТЫ", "en": "CARDS"},
    "link_all": {"uz": "Hammasi ›", "ru": "Все ›", "en": "All ›"},
    "link_history": {"uz": "Tarix ›", "ru": "История ›", "en": "History ›"},

    # ---- New / edit operation ----
    "title_newop": {"uz": "YANGI AMAL", "ru": "НОВАЯ ОПЕРАЦИЯ", "en": "NEW OPERATION"},
    "title_editop": {"uz": "TAHRIRLASH", "ru": "ИЗМЕНИТЬ", "en": "EDIT OPERATION"},
    "close": {"uz": "Yopish", "ru": "Закрыть", "en": "Close"},
    "seg_expense": {"uz": "XARAJAT", "ru": "РАСХОД", "en": "EXPENSE"},
    "seg_income": {"uz": "KIRIM", "ru": "ДОХОД", "en": "INCOME"},
    "seg_transfer": {"uz": "O'TKAZMA", "ru": "ПЕРЕВОД", "en": "TRANSFER"},
    "lbl_amount": {"uz": "SUMMA", "ru": "СУММА", "en": "AMOUNT"},
    "lbl_category": {"uz": "KATEGORIYA", "ru": "КАТЕГОРИЯ", "en": "CATEGORY"},
    "lbl_payment": {"uz": "TO'LOV USULI", "ru": "СПОСОБ ОПЛАТЫ", "en": "PAYMENT METHOD"},
    "lbl_account_in": {"uz": "QAYSI HISOBGA", "ru": "НА КАКОЙ СЧЁТ", "en": "TO ACCOUNT"},
    "lbl_from": {"uz": "QAYERDAN", "ru": "ОТКУДА", "en": "FROM"},
    "lbl_to": {"uz": "QAYERGA", "ru": "КУДА", "en": "TO"},
    "lbl_note": {"uz": "IZOH", "ru": "ЗАМЕТКА", "en": "NOTE"},
    "note_ph": {"uz": "ixtiyoriy", "ru": "необязательно", "en": "optional"},
    "lbl_date": {"uz": "SANA", "ru": "ДАТА", "en": "DATE"},
    "today_at": {"uz": "Bugun, {time}", "ru": "Сегодня, {time}", "en": "Today, {time}"},
    "yesterday_at": {"uz": "Kecha, {time}", "ru": "Вчера, {time}", "en": "Yesterday, {time}"},
    "no_acc_currency": {"uz": "{currency} hisob yo'q", "ru": "Нет счетов в {currency}",
                        "en": "No {currency} accounts"},
    "no_categories": {"uz": "Kategoriya yo'q", "ru": "Категорий нет", "en": "No categories"},
    "archived_tag": {"uz": "arxiv", "ru": "архив", "en": "archived"},
    "delete_op": {"uz": "Amalni o'chirish", "ru": "Удалить операцию", "en": "Delete operation"},
    "confirm_delete_op": {
        "uz": "Amal o'chirilsinmi? Hisob balansi qayta hisoblanadi.",
        "ru": "Удалить операцию? Баланс счёта будет пересчитан.",
        "en": "Delete this operation? The account balance is recalculated.",
    },
    "confirm_delete_transfer": {
        "uz": "O'tkazma o'chirilsinmi? Ikkala hisob balansi tiklanadi.",
        "ru": "Удалить перевод? Балансы обоих счетов будут восстановлены.",
        "en": "Delete this transfer? Both account balances are restored.",
    },
    "op_deleted": {"uz": "Amal o'chirildi", "ru": "Операция удалена", "en": "Operation deleted"},
    "warn_over_limit": {
        "uz": "⚠️ {names}: qarz kredit limitidan oshdi", "ru": "⚠️ {names}: долг выше кредитного лимита",
        "en": "⚠️ {names}: the debt is above the credit limit",
    },
    "err_category": {"uz": "Kategoriyani tanlang", "ru": "Выберите категорию", "en": "Pick a category"},
    "err_account": {"uz": "Hisobni tanlang", "ru": "Выберите счёт", "en": "Pick an account"},
    "err_same_account": {"uz": "Ikki xil hisobni tanlang", "ru": "Выберите два разных счёта",
                         "en": "Pick two different accounts"},
    "err_currency_mismatch": {"uz": "Hisob valyutasi mos emas", "ru": "Валюта счёта не совпадает",
                              "en": "The account currency does not match"},
    "err_date": {"uz": "Sana noto'g'ri (kelajakdagi sana bo'lmaydi)", "ru": "Неверная дата (будущая нельзя)",
                 "en": "Invalid date (it cannot be in the future)"},
    "err_note": {"uz": "Izoh juda uzun (200 belgigacha)", "ru": "Слишком длинная заметка (до 200 символов)",
                 "en": "The note is too long (up to 200 characters)"},
    "err_locked": {"uz": "Buni o'zgartirib bo'lmaydi", "ru": "Это нельзя изменить", "en": "This cannot be changed"},
    "err_start": {"uz": "Avval botda /start bosing", "ru": "Сначала нажмите /start в боте",
                  "en": "Send /start to the bot first"},
    "err_rate": {"uz": "Kurs noto'g'ri", "ru": "Неверный курс", "en": "Invalid rate"},
    "err_salary_day": {"uz": "Kun 1 dan 28 gacha", "ru": "День от 1 до 28", "en": "The day is 1 to 28"},

    # ---- History ----
    "search_ph": {"uz": "Qidirish: taksi, kofe…", "ru": "Поиск: такси, кофе…", "en": "Search: taxi, coffee…"},
    "search": {"uz": "Qidirish", "ru": "Поиск", "en": "Search"},
    "f_all": {"uz": "Hammasi", "ru": "Все", "en": "All"},
    "f_expense": {"uz": "Chiqim", "ru": "Расход", "en": "Expenses"},
    "f_income": {"uz": "Kirim", "ru": "Доход", "en": "Income"},
    "f_all_accounts": {"uz": "Barcha hisoblar", "ru": "Все счета", "en": "All accounts"},
    "day_today": {"uz": "BUGUN", "ru": "СЕГОДНЯ", "en": "TODAY"},
    "day_yesterday": {"uz": "KECHA", "ru": "ВЧЕРА", "en": "YESTERDAY"},
    "history_hint": {"uz": "Amalni bosing: tahrirlash yoki o'chirish",
                     "ru": "Нажмите на операцию, чтобы изменить или удалить",
                     "en": "Tap an operation to edit or delete it"},
    "nothing_found": {"uz": "Hech narsa topilmadi", "ru": "Ничего не найдено", "en": "Nothing found"},
    "load_more": {"uz": "YANA YUKLASH", "ru": "ПОКАЗАТЬ ЕЩЁ", "en": "LOAD MORE"},

    # ---- Report ----
    "seg_week": {"uz": "HAFTA", "ru": "НЕДЕЛЯ", "en": "WEEK"},
    "seg_month": {"uz": "OY", "ru": "МЕСЯЦ", "en": "MONTH"},
    "seg_year": {"uz": "YIL", "ru": "ГОД", "en": "YEAR"},
    "stamp_more": {"uz": "KO'PROQ", "ru": "БОЛЬШЕ", "en": "MORE"},
    "stamp_less": {"uz": "KAMROQ", "ru": "МЕНЬШЕ", "en": "LESS"},
    "stamp_same": {"uz": "TENG", "ru": "СТОЛЬКО ЖЕ", "en": "SAME"},
    "vs_week": {"uz": "o'tgan haftaning shu kunlariga nisbatan", "ru": "к тем же дням прошлой недели",
                "en": "vs the same days of last week"},
    "vs_month": {"uz": "o'tgan oyga nisbatan", "ru": "по сравнению с прошлым месяцем", "en": "vs last month"},
    "vs_year": {"uz": "o'tgan yilning shu kunlariga nisbatan", "ru": "к тем же дням прошлого года",
                "en": "vs the same days of last year"},
    "remainder": {"uz": "QOLDIQ", "ru": "ОСТАТОК", "en": "LEFT OVER"},
    "report_empty": {"uz": "Bu davrda hali amallar yo'q", "ru": "В этом периоде операций пока нет",
                     "en": "No operations in this period yet"},
    "no_sub": {"uz": "subkategoriyasiz", "ru": "без подкатегории", "en": "no subcategory"},
    "ai_advice": {"uz": "AI maslahat:", "ru": "Совет AI:", "en": "AI advice:"},
    "ai_loading": {"uz": "AI maslahat tayyorlanmoqda…", "ru": "AI готовит совет…", "en": "AI is preparing advice…"},

    # ---- Settings ----
    "title_settings": {"uz": "SOZLAMALAR", "ru": "НАСТРОЙКИ", "en": "SETTINGS"},
    "sec_money": {"uz": "PUL", "ru": "ДЕНЬГИ", "en": "MONEY"},
    "sec_ai": {"uz": "AI MASLAHAT", "ru": "AI-СОВЕТЫ", "en": "AI ADVICE"},
    "sec_lang": {"uz": "TIL", "ru": "ЯЗЫК", "en": "LANGUAGE"},
    "set_cards": {"uz": "Kartalar va hisoblar", "ru": "Карты и счета", "en": "Cards and accounts"},
    "set_salary": {"uz": "Maosh kuni", "ru": "День зарплаты", "en": "Salary day"},
    "set_salary_hint": {"uz": "Oy shu kundan hisoblanadi", "ru": "С этого дня начинается месяц",
                        "en": "Your month starts on this day"},
    "set_rate": {"uz": "Dollar kursi", "ru": "Курс доллара", "en": "USD rate"},
    "rate_auto": {"uz": "AVTO", "ru": "АВТО", "en": "AUTO"},
    "rate_manual": {"uz": "QO'LDA", "ru": "ВРУЧНУЮ", "en": "MANUAL"},
    "rate_input": {"uz": "1 USD = ? so'm", "ru": "1 USD = ? сум", "en": "1 USD = ? UZS"},
    "rate_saved": {"uz": "Kurs saqlandi", "ru": "Курс сохранён", "en": "Rate saved"},
    "set_budgets": {"uz": "Oylik limitlar", "ru": "Месячные лимиты", "en": "Monthly limits"},
    "budgets_count": {"uz": "{n} ta kategoriya limiti", "ru": "лимитов по категориям: {n}",
                      "en": "category limits: {n}"},
    "adv_weekly": {"uz": "Haftalik maslahat", "ru": "Еженедельный совет", "en": "Weekly advice"},
    "adv_weekly_hint": {"uz": "Har dushanba", "ru": "Каждый понедельник", "en": "Every Monday"},
    "adv_monthly": {"uz": "Oylik maslahat", "ru": "Ежемесячный совет", "en": "Monthly advice"},
    "adv_monthly_hint": {"uz": "Maosh kunida", "ru": "В день зарплаты", "en": "On your salary day"},
    "ai_off_note": {"uz": "AI sozlanmagan: maslahatlar yuborilmaydi", "ru": "AI не настроен: советы не приходят",
                    "en": "AI is not configured: no advice is sent"},
    "sw_on": {"uz": "Yoqilgan", "ru": "Включено", "en": "On"},
    "sw_off": {"uz": "O'chirilgan", "ru": "Выключено", "en": "Off"},
    "dec": {"uz": "Kamaytirish", "ru": "Уменьшить", "en": "Decrease"},
    "inc": {"uz": "Oshirish", "ru": "Увеличить", "en": "Increase"},

    # ---- Budgets ----
    "title_budgets": {"uz": "OYLIK LIMITLAR", "ru": "МЕСЯЧНЫЕ ЛИМИТЫ", "en": "MONTHLY LIMITS"},
    "budget_add": {"uz": "LIMIT QO'SHISH", "ru": "ДОБАВИТЬ ЛИМИТ", "en": "ADD A LIMIT"},
    "budget_new": {"uz": "YANGI LIMIT", "ru": "НОВЫЙ ЛИМИТ", "en": "NEW LIMIT"},
    "budget_edit": {"uz": "LIMITNI O'ZGARTIRISH", "ru": "ИЗМЕНИТЬ ЛИМИТ", "en": "EDIT LIMIT"},
    "budget_empty": {"uz": "Hali limit yo'q", "ru": "Лимитов пока нет", "en": "No limits yet"},
    "budget_period": {"uz": "Oy: {start} — {end}", "ru": "Месяц: {start} — {end}", "en": "Month: {start} — {end}"},
    "lbl_month_limit": {"uz": "OYLIK LIMIT", "ru": "ЛИМИТ НА МЕСЯЦ", "en": "MONTHLY LIMIT"},
    "budget_delete": {"uz": "Limitni o'chirish", "ru": "Удалить лимит", "en": "Delete the limit"},
    "confirm_budget_delete": {"uz": "«{name}» limiti o'chirilsinmi?", "ru": "Удалить лимит «{name}»?",
                              "en": "Delete the limit of “{name}”?"},
    "budget_deleted": {"uz": "Limit o'chirildi", "ru": "Лимит удалён", "en": "Limit deleted"},
    "budget_note": {
        "uz": "Limitning 80% va 100% ga yetganda bot chatga xabar yuboradi.",
        "ru": "Когда расходы дойдут до 80% и 100% лимита, бот напишет в чат.",
        "en": "The bot messages you in the chat when spending reaches 80% and 100% of a limit.",
    },
    "cancel": {"uz": "BEKOR QILISH", "ru": "ОТМЕНА", "en": "CANCEL"},

    # ---- Users (owners / superadmins only) ----
    "sec_manage": {"uz": "BOSHQARUV", "ru": "УПРАВЛЕНИЕ", "en": "MANAGEMENT"},
    "set_users": {"uz": "Foydalanuvchilar", "ru": "Пользователи", "en": "Users"},
    "users_count": {"uz": "{n} kishiga ruxsat · faqat admin ko'radi", "ru": "доступ у {n} чел. · видит только админ",
                    "en": "{n} with access · admins only"},
    "title_users": {"uz": "FOYDALANUVCHILAR", "ru": "ПОЛЬЗОВАТЕЛИ", "en": "USERS"},
    "users_add_title": {"uz": "USERNAME BILAN QO'SHISH", "ru": "ДОБАВИТЬ ПО USERNAME", "en": "ADD BY USERNAME"},
    "users_add": {"uz": "QO'SHISH", "ru": "ДОБАВИТЬ", "en": "ADD"},
    "users_pick": {"uz": "Kontaktlardan tanlash", "ru": "Выбрать из контактов", "en": "Pick from contacts"},
    "users_hint": {
        "uz": "Username bo'lmasa: kontaktlardan tanlang yoki pastdagi ro'yxatdan toping.",
        "ru": "Нет username: выберите из контактов или найдите в списке ниже.",
        "en": "No username? Pick from contacts or find them in the list below.",
    },
    "users_granted": {"uz": "RUXSATI BOR", "ru": "ЕСТЬ ДОСТУП", "en": "HAVE ACCESS"},
    "users_pending": {"uz": "KUTILMOQDA", "ru": "ОЖИДАЕТ", "en": "PENDING"},
    "users_pending_hint": {"uz": "botni hali ochmagan", "ru": "ещё не открыл бота", "en": "hasn't opened the bot yet"},
    "users_none": {"uz": "Hali hech kimga ruxsat berilmagan", "ru": "Доступа пока ни у кого нет",
                   "en": "Nobody has access yet"},
    "users_visitors": {"uz": "BOTNI BOSHLAGANLAR", "ru": "ЗАПУСКАЛИ БОТА", "en": "STARTED THE BOT"},
    "users_search": {"uz": "Ism yoki username", "ru": "Имя или username", "en": "Name or username"},
    "users_no_visitors": {"uz": "Hech kim topilmadi", "ru": "Никого не найдено", "en": "Nobody found"},
    "users_no_username": {"uz": "username yo'q", "ru": "без username", "en": "no username"},
    "users_grant": {"uz": "+ QO'SHISH", "ru": "+ ДОБАВИТЬ", "en": "+ ADD"},
    "users_remove": {"uz": "Ruxsatni olib tashlash", "ru": "Забрать доступ", "en": "Remove access"},
    "users_confirm_remove": {"uz": "{name} ruxsati olib tashlansinmi?", "ru": "Забрать доступ у {name}?",
                             "en": "Remove access of {name}?"},
    "users_added": {"uz": "Ruxsat berildi", "ru": "Доступ выдан", "en": "Access granted"},
    "users_removed": {"uz": "Ruxsat olib tashlandi", "ru": "Доступ забран", "en": "Access removed"},
    "users_pick_sent": {"uz": "Botdagi tugmani bosing", "ru": "Нажмите кнопку в чате с ботом",
                        "en": "Tap the button in the bot chat"},
    "err_username": {"uz": "Username noto'g'ri (5–32 belgi: harf, raqam, _)",
                     "ru": "Неверный username (5–32 символа: буквы, цифры, _)",
                     "en": "Invalid username (5–32 chars: letters, digits, _)"},
    "err_exists": {"uz": "Bu odamda allaqachon ruxsat bor", "ru": "У этого человека уже есть доступ",
                   "en": "This person already has access"},
    "err_not_manager": {"uz": "Faqat admin uchun", "ru": "Только для админа", "en": "Admins only"},
}


def webapp_texts(lang: Optional[str]) -> dict:
    """All Mini App texts in one language (missing ones fall back to English)."""
    lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
    return {key: variants.get(lang) or variants["en"] for key, variants in WEBAPP_TEXTS.items()}
