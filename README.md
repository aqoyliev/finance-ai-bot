# aiogram-bot-template

A clean, batteries-included starter template for building Telegram bots with
[aiogram](https://docs.aiogram.dev/) 2.x. It gives you a sensible project
layout, throttling, an error handler, admin start-up notifications and bot
command registration out of the box, so you can focus on writing handlers.

> Use the green **"Use this template"** button on GitHub to spin up a new bot
> from this repository.

## Features

- 📁 Structured layout — handlers, keyboards, middlewares, states, filters and utils are pre-wired
- 🚦 Anti-flood throttling middleware
- 🛟 Centralized error handler for common Telegram API exceptions
- 🔔 Notifies admins when the bot starts
- 🧭 Registers default bot commands (`/start`, `/help`) automatically
- 🔐 Configuration via a `.env` file (`environs`)
- 🇬🇧 All code comments are written in English; bot messages are translated (uz / ru / en)

## Finance bot

A private personal-finance bot for a single owner, built on this template.

### Features

The chat is for input and questions; everything else lives in the 📱 Mini App.

- 🔐 Private: only Telegram IDs listed in `ADMINS` can use it; anyone else gets one short "private bot" reply
- 🌐 Uzbek (Latin), Russian and English. The language is chosen on the first `/start` and can be changed in the
  Mini App (Settings → Til). Starter categories and one account, Cash (UZS), are created once, in the language picked
  first; the user adds their own cards in the Mini App
- 💬 **Chat:** only `/start` and `/help`. Type or say an operation, send a receipt photo or a bank SMS (see AI input
  below): it is saved at once and confirmed with a short card. Questions about your data are answered by Ask AI.
  Weekly / monthly AI advice and limit alerts arrive in the chat
- 📱 **Mini App** (see below): Home (balance, the month's expense and income, monthly limit, cards, last operations),
  ➕ new operation (expense, income, transfer; edit and delete from History), History (search, filters, by day),
  Report (week / month / year, categories, change vs the previous period, AI advice) and Settings (cards, salary day,
  USD rate, monthly limits, AI advice switches, language)
- 💳 Accounts (cash, debit, credit; UZS or USD) with the card type and the last 4 digits; credit cards show debt, limit
  and available credit; deleting an account with operations archives it (history kept)
- 🔁 Transfers between own accounts of the same currency; a transfer to a credit card repays its debt.
  Transfers are never counted as income or expense
- ⚠️ Warning when an expense pushes a credit card's debt above its limit
- 📊 Reports per financial month (it starts on the salary day), week or calendar year
- 🎯 Monthly budgets per expense category and 🔔 alerts at 80% / 100% of a budget or of a credit card limit
- 🤖 AI input: record operations from free text, a voice message, a receipt photo or a forwarded bank SMS,
  without confirmation (see below)
- 💬 Ask AI: type a question about your own data in plain language; plus 📅 weekly and 📆 monthly AI advice

All texts live in `utils/i18n.py` (`TEXTS` for the chat, `WEBAPP_TEXTS` for the Mini App); operations are written
through `record_operation` / `record_transfer` in `utils/db_api/operations.py`, from AI input and from the Mini App alike.

### Bot surface

| Input | Answer |
|-------|--------|
| `/start` | Language picker on the first contact; afterwards a short "what to do" text (type, say or send a receipt / SMS; everything else is in the app) with an inline **📱 Ilovani ochish** Web App button (when `WEBAPP_URL` is https). The message is sent with `ReplyKeyboardRemove`, so chats that still show the old 📊 / 💳 / ⚙️ keyboard lose it; the button is then attached to it (if Telegram refuses that edit, it follows in a short second message) |
| `/help` | The same idea, a little longer: AI input, questions and advice, what each app screen does, with the app button |
| Text, voice, photo, file, bank SMS | AI input or Ask AI (below) |
| An old command (`/expense`, `/income`, `/transfer`, `/salaryday`, `/rate`, `/report`, `/balance`, `/settings`), an old reply-keyboard button (`📊 Report`, `💳 Balance`, `⚙️ Settings` in any language, exact label) or a button of an old inline screen | A short hint ("balance, report, history and settings are in the 📱 app now") with the app button; nothing is sent to the AI |

On start-up `utils/set_bot_commands.py` deletes the bot commands of the default scope for the default list and for
each language code (`uz`, `ru`, `en`), then registers only `/start` and `/help`, so no stale command stays in a
client's menu. The chat menu button of every admin opens the Mini App's Home.

### Receipt cards

The weekly / monthly advice comes with a receipt card (`utils/cards.py`, templates in
`templates/cards/`): Jinja2 HTML rendered to a 1080 px wide PNG (height follows the content) by headless Chromium
through Playwright. The JetBrains Mono font is vendored in `assets/fonts/` (SIL OFL, `OFL.txt`) and embedded into
the page, so rendering works offline.

- **Weekly receipt** (with the Monday advice): categories with the change vs the previous week, total, a 7-day
  barcode (biggest day in red), the biggest single expense with its weekday and the most-used budget.
- **Monthly receipt** (with the advice on the salary day, for the period that just ended): up to 8 categories (the
  rest folded into "Other"), total vs the previous period, income / expenses / balance, a barcode per 7 days, top 3
  expenses, budgets as `[#######---]` bars and the payment method split (cash / debit / credit card) with credit
  limit use.
- **Report** (the running financial period; used by `cards.advice_card("now")`): categories with share bars and change,
  total vs the previous period (or its same days), over-budget categories.
- No expenses in the window: an "empty" receipt. Expenses in both UZS and USD: one section per currency, never
  converted.

The stamp shows the change of total spending (▲ red = spent more, ▼ blue = less). The advice text is the photo's
caption when it fits 1024 characters, otherwise the photo is followed by the text as a message.

If the card cannot be rendered, `cards.card_or_chart` falls back to the matplotlib chart of `utils/charts.py` (a donut
for up to 8 categories, bars for more), and without either the advice is text only.

One Chromium is started lazily on the first card, reused (at most 2 pages at a time) and closed on shutdown. If
Playwright or Chromium is missing, crashes or a card takes longer than 25 s, the problem is logged and the bot falls
back to the matplotlib chart, then to text; a failed browser start is retried after 5 minutes.

Setup: `pip install -r requirements.txt`, then `python -m playwright install chromium`. In Docker use
`playwright install --with-deps chromium` (it also installs the system libraries Chromium needs).

### USD exchange rate

By default the bot uses the **official rate of the Central Bank of Uzbekistan** (`https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/`,
the `Rate` and `Date` of the `USD` item). cbu.uz is geo-blocked outside Uzbekistan (it times out on Railway), so
`utils/rates.py` fetches the rate through a **fallback chain** with aiohttp and the User-Agent `finance-ai-bot`:

1. cbu.uz (5 s timeout), source `cbu`;
2. `https://open.er-api.com/v6/latest/USD` (`rates.UZS`, 10 s), source `market`;
3. `https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json` (`usd.uzs`, 10 s), source `market`.

Each value must be a finite number with 1000 < rate < 100000, otherwise that source counts as failed. The date is the
source's own date, or today in Asia/Tashkent if it gives none. The rate is cached in memory for 6 hours and the last good
value (with its source) is stored in the `official_rates` table, so a restart or an outage still has a rate. A background
task (started in `on_startup`, cancelled on shutdown) refreshes it at startup and then every 6 hours (every 30 minutes
after a failure); a failed fetch only logs a warning and keeps the last value. If no source ever answered, combined totals
and cross-currency budget amounts are simply skipped.

- Home and Settings in the Mini App show the rate in use and its source: Markaziy bank (official), Bozor kursi
  (international market rate, when the Central Bank was unreachable) or Qo'lda (manual), with its date. The same source
  (and its date) is given to the AI in the context line and the `get_exchange_rate` tool.
- Settings → Dollar kursi → QO'LDA sets your own override (`PUT /api/settings {"rate_mode": "manual", "rate": "12850"}`,
  a positive number below 10 000 000 with up to 6 decimals); AVTO removes it and returns to the Central Bank rate.
- The AI assistant never states a rate from memory: the rate, its source and date are put into the context line and the
  `get_exchange_rate` tool result (and into the advice figures), and the system prompts forbid quoting any other.

Migration `0006` creates `official_rates` and deletes all existing manual rates (`exchange_rates`), so everyone starts
on the default rate. Migration `0007` adds `official_rates.source` (`cbu` | `market`, existing rows become `cbu`).

### Budgets and alerts

Mini App → Settings → Oylik limitlar: pick an expense category, then set, change or remove its monthly limit (UZS or
USD; the month is the financial period). The list shows `spent / limit`, the percentage and a striped bar for every
budget; Home shows the sum of all limits.
Spending in the other currency counts towards a budget at the USD rate in use (see [USD exchange rate](#usd-exchange-rate)); without any known rate it is not converted.

After an expense is saved (in the Mini App or from AI input), edited (amount, category or account) or after a
transfer touches a credit card, the bot checks the budgets of the affected categories and the affected credit cards
and sends **one message per threshold (80% and 100%) per period** for each category / card:

- sent alerts are stored in `alerts_sent` keyed by the period start, so every new period starts clean;
- deleting or lowering an expense does not "unsend" anything, and crossing a threshold again within the same
  period is not announced again;
- one change that jumps over both thresholds produces only the 100% alert;
- changing or removing a budget limit clears that category's alerts for a fresh start;
- the "debt above the limit" warning of the save confirmation (the chat card, or the Mini App's toast) stays; its card
  does not get a second 100% message for the same save.

Checks run in one service, `db.check_alerts` (`utils/db_api/alerts.py`), called through
`utils/notify_alerts.send_alerts` from AI input and from the Mini App API (`utils/miniapp/screens.py`) after saves and
edits; the message goes to the chat through the bot either way.

### AI provider (Google Gemini or Anthropic Claude)

`AI_PROVIDER` selects the provider for everything AI: `gemini` (default) or `claude`. Both implement the same
client interface (`utils/ai/core.py`: `get_client()` returns the configured one), so AI input, Ask AI and
advice work the same way with either. Only Gemini has audio input, so voice messages need `AI_PROVIDER=gemini`.

| Provider | Extraction (receipts, SMS, text, voice) | Ask AI and advice | Key |
|----------|------------------------------------------|-------------------|-----|
| `gemini` | `gemini-3.5-flash-lite` | `gemini-3.8-flash` | `GEMINI_API_KEY` ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) |
| `claude` | `claude-haiku-5-5` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |

Approximate Gemini cost (paid tier, [pricing page](https://aistudio.google.com/docs/pricing), November 2026):
`gemini-3.5-flash-lite` is $0.30 / 1M input and $2.50 / 1M output tokens, so one receipt, SMS or short voice
message is roughly $0.002-0.004; `gemini-3.8-flash` is $0.75 / $3.75 per 1M until 31.12.2026 ($1.50 / $7.50
from 01.01.2027), so an Ask AI answer with a few tool calls or one advice is roughly $0.01-0.04.

### Saved operation card

Every operation saved from the chat (AI input) is confirmed with the same short HTML card
(`utils/misc/texts.operation_card`, labels in uz / ru / en):

```
💸 XARAJAT
──────────────
💰 Summa: 25 000 so'm
🏷 Kategoriya: Transport › Taksi
💳 To'lov: Naqd
🕐 Vaqt: 04 Noy, 22:15
──────────────
📝 taksi
```

An income starts with 💰 KIRIM (and shows the account), a transfer with 🔁 O'TKAZMA and From / To lines; the note
line is left out when there is no note. A credit card pushed over its limit adds the ⚠️ warning under the card.

### AI input

Just send the bot any of these:

- **free text** in Uzbek, Russian or English: `taksi 25000 naqd`, `кофе 18 тысяч наличными`,
  `got salary 12m to hamkorbank`; several operations in one message are fine
- a **voice message** or audio file (Gemini only; up to 2 minutes and 14 MB): `taksiga 25 ming to'ladim naqd`;
  it is transcribed and parsed in one request, like text
- a **receipt photo** (or an image / PDF sent as a file; Gemini: JPEG, PNG, WebP, HEIC up to 14 MB; Claude: JPEG, PNG, GIF, WebP up to 5 MB; PDF up to 14 MB); the total paid is used, not the individual lines
- a **forwarded / pasted bank SMS** or notification (Uzcard, Humo, Visa; debit and credit)

There is no confirmation step: every recognized operation is saved right away and confirmed with a card.

- **Payment method (account).** If it is clear (card digits from an SMS or receipt, "naqd" / "karta" / a bank
  name, a valid account), the operation is saved at once. Otherwise the bot asks only "💳 Which payment method?"
  with one button per account (of the operation's currency) and saves on tap; typing a short account name
  (`naqd`, `uob`) works too. When several operations of one message lack the account, it is asked once and the
  answer applies to all of them. With the Mini App on, the last button, "➕ Yangi karta qo'shish", is a Web App button
  that opens the app's new-card form (`#/new`); the operations keep waiting, and typing the new card's name in the chat
  afterwards saves them to it (the question says so). Other typed text without digits gets a short hint ("pick a
  button or type the account name"); text with an operation in it is analyzed as usual. With only one account there is
  nothing to ask: the operation is saved to it.
- **Category.** An expense or income without a recognizable category goes to "Other" ("Boshqa" / "Прочее";
  "Other income" for incomes), created if the user has none.
- **Amount.** An operation without an amount is not saved; the bot answers that no amount was understood.
- A transfer whose receiving account is unclear is not saved; the bot points to the Mini App (➕ → O'tkazma).
- **Duplicates.** The same SMS, photo or file sent again is not saved twice ("already saved"). The same amount on
  the same account within 10 minutes (e.g. a typed taxi and then its bank SMS) is saved, with a warning that
  points to the Mini App's History for deleting it. Typed text has no fingerprint, so writing "coffee 18000"
  again on another day is a new expense.
- Budget and credit limit alerts follow the save confirmations. Saved rows have `source = "ai"`.

With `AI_PROVIDER=claude` voice messages get a short reply that voice input needs Google Gemini (Claude has no
audio input). Longer voice messages get a "too long" reply before anything is downloaded.

How it works: `utils/ai/core.py` sends the input (image/PDF/audio bytes inline, no separate OCR or speech-to-text)
plus a list of your accounts and categories to the extraction model and asks for JSON that follows a fixed
schema (Gemini: `response_json_schema` with JSON mode, low thinking level; Claude: structured outputs,
`output_config.format`).
`utils/ai/parser.py` never trusts the answer: amounts are re-parsed (`125 000,00`, `125.000`, `18 ming`, `12m`),
the currency must be UZS/USD, the account must be yours and in that currency, the category must exist;
anything doubtful is left empty (then the account is asked, the category falls back to "Other"). Card digits from an SMS (`*1234`) match the account
whose **last 4 digits** were saved in the Mini App; an account without saved digits still matches when its
**name contains those 4 digits** (e.g. `UOB 1234`; migration `0005` copied such digits into the new field).

Old commands and old reply-keyboard labels are handled before AI input (`handlers/users/legacy.py`), so they never
reach the AI. Without the key of the selected provider free text gets an "AI input is not configured" answer that
points to manual entry in the Mini App.

> **Privacy:** receipts and texts you send for AI input, together with the names of your accounts and
> categories, are sent to the selected AI provider (Google Gemini API or Anthropic Claude API) for
> processing. Balances and history are not sent.

### Ask AI and automatic advice

**Ask AI.** Just type a question ("how much did I spend on taxi this month?", "am I spending more than last
month?", "how much credit is left?"): the extraction model classifies every free-text message as an
*operation*, a *question* or *other*; questions go to Ask AI, operations are saved. Follow-up questions work
("and last month?") because the conversation is kept and the extraction model is told about it; `/start` or a
newly saved operation starts a fresh one. Photos, files and bank SMS always go to AI
input.

How it works (`utils/ai/assistant.py`, `utils/ai/tools.py`): the analysis model (`gemini-3.8-flash` or
`claude-opus-5-5`) gets
read-only **client-side tools** backed by the service layer instead of a database dump:
`get_period_summary`, `get_category_breakdown`, `search_transactions`, `get_accounts`, `get_budgets`,
`get_categories`, `get_exchange_rate` (the official or manual rate with its source and date; strict JSON schemas; results are compact JSON with amounts and
currency; transfers are never income or expense; Gemini gets them as function declarations). The bot runs
the tool loop itself (at most 6 model requests
and 4 minutes per question) and answers in your language as plain text. The conversation is kept in memory
(FSM) for an hour; after 6 questions it is compacted to the last 3 question/answer pairs.

**Advice.** 📅 a weekly summary every **Monday at 09:00** (Tashkent time): the last 7 days vs the 7 before,
top categories, unusual spending, budget status and 2-4 saving tips. 📆 A monthly review at **09:00 on the
first day of a new financial month** (your salary day): the finished period vs the one before, budgets,
credit cards and advice for the new period. Turn either off in the Mini App (Settings → AI maslahat); the automatic
advice carries a button to those settings. The Mini App's Report shows an advice on the running period (or the last 7
days for HAFTA), generated on demand. Nothing is sent for a window without income or expenses.
The scheduler (`utils/advice_scheduler.py`) is an asyncio task started in `on_startup` that checks once a
minute; what was sent is stored on the user row (migration `0004`), so a restart never sends twice and advice
missed while the bot was down at 09:00 is sent on the next start the same day. The model gets pre-computed
summaries, not raw rows.

> **Privacy:** your questions, the data the assistant looks up to answer them (totals, categories,
> matching operations, balances) and the summaries used for advice are sent to the selected AI provider.

### Mini App

A Telegram Mini App with every screen except the chat input, served by the bot process itself: `on_startup` starts an
aiohttp web server on `PORT` (default `8080`, all interfaces) next to long polling and stops it on shutdown. The page is
plain HTML + CSS + JS in `webapp/` (no build step, hash routes), drawn as paper receipts in JetBrains Mono (served from
`assets/fonts/`, no Google Fonts); the server code is in `utils/miniapp/`. Home, History, Report and Settings share a
bottom tab bar (ASOSIY, TARIX, the raised red ➕, HISOBOT, SOZLAMA); the content scrolls above it.

- **Asosiy (Home, `#/`):** the financial month's name and the USD rate with its source (Central Bank / market /
  manual); the total balance in UZS (USD accounts converted at that rate, or listed separately when no rate is known);
  this financial month's expense and income (from the salary day, like the reports); the monthly limit (sum of all
  budgets vs the spending in those categories, converted to UZS) only when budgets exist; a horizontal strip of cards
  (each opens its card, "Hammasi ›" the list) and the last 3 operations with "Tarix ›".
- **➕ Yangi amal (`#/op/new`):** XARAJAT / KIRIM / O'TKAZMA, a big amount with UZS / USD, category chips with
  subcategory chips (the user's own categories; there is no "+ other": the backend cannot create categories), payment
  method chips (accounts of the currency; a transfer gets From and To chips instead), note and date / time (now by
  default, any past moment can be picked). SAQLASH calls `record_operation` / `record_transfer`, so balances, credit
  cards and transfers behave exactly as in the chat, and limit alerts are sent to the chat through the bot. A credit
  card pushed over its limit is reported in the app (the chat does not repeat it as a 100% alert).
- **Edit (`#/op/{id}`, from History, Home or a card):** the same screen, prefilled, with "Amalni o'chirish" (confirmed).
  Amount, category, account (same currency), note and time can change, through `update_amount`, `update_category`,
  `update_account` and `update_details`; the kind, the currency and the accounts of a transfer are fixed. Alerts follow
  an edit as they did in the chat. Deleting a transfer removes both legs.
- **Tarix (`#/history`):** search (note, category, subcategory), Hammasi / Chiqim / Kirim chips and an account
  dropdown; grouped by day (BUGUN / KECHA / dd.mm), 30 at a time with automatic loading and a "load more" button.
- **Hisobot (`#/report`):** HAFTA (Monday to Sunday) / OY (the financial month) / YIL (the calendar year). The expense
  total with a stamp of the change vs the same number of days of the previous period (▲ red = more, ▼ blue = less),
  categories with striped bars (the biggest in red; tap one for its subcategories), income and the remainder. With a USD
  rate everything is summed in UZS, otherwise each currency has its own slip. An AI advice box is loaded separately
  (skeleton first; `assistant.advice`, "weekly" for the week, the running period otherwise; reused for 30 minutes) and
  hidden when AI is off, has nothing to say or fails.
- **Sozlamalar (`#/settings`):** Kartalar va hisoblar (the cards screens), Maosh kuni with − / + (1-28), Dollar kursi
  AVTO / QO'LDA (QO'LDA reveals the rate input; AVTO removes the override; the current rate and its source are shown),
  Oylik limitlar (a list of category limits with used %, add, change and delete), weekly / monthly AI advice switches
  and the language (O'ZBEKCHA / РУССКИЙ / ENGLISH, stored for the bot too; the app reloads its texts).
- **Kartalarim (`#/cards`), Karta tafsiloti (`#/card/{id}`), Yangi karta / Tahrirlash (`#/new`, `#/edit/{id}`):** as
  before: balances, add / edit / delete (archive with history), the month's totals and the last operations of a card.
  Only the last 4 digits are stored, never the card number; two active accounts cannot share them. Editing the current
  balance moves the opening balance by the difference. The currency of an account with operations cannot change.
- Texts are in uz / ru / en (`WEBAPP_TEXTS`). The Telegram Back button returns to where the user came from.

**Opening it.** With `WEBAPP_URL` set to the public `https://` address of the server, each admin's chat menu button opens
Home, `/start` and `/help` carry the "📱 Ilovani ochish" button, the AI account question ends with "➕ Yangi karta
qo'shish" (opens `#/new`) and the automatic advice links to Settings. Without `WEBAPP_URL`, or with a non-https one,
the server still runs but the bot shows no Mini App buttons (Telegram only opens https Mini Apps).

**Security.** Every `/api/` request carries `Telegram.WebApp.initData` in the `X-Telegram-Init-Data` header. The server
checks its HMAC-SHA256 signature with the bot token (secret = `HMAC_SHA256("WebAppData", BOT_TOKEN)`), refuses data
older than 24 hours and takes the user id from it; only IDs in `ADMINS` get through (401 for missing / bad /
expired data, 403 for anyone else). Every query is scoped to that user id, so another user's accounts, operations and
budgets answer 404. initData and the token are never logged. An admin who never chose a language gets 409 `start`.

**API** (JSON; amounts are integers in minor units; every input is validated on the server, errors are
`{"error": code}` with 400 / 404 / 409):

| Endpoint | Purpose |
|----------|---------|
| `GET /api/me` | language, texts, whether AI is configured |
| `GET /api/home` | month, rate, balance, month expense / income, limit (or null), accounts, last 3 operations |
| `GET /api/form` | categories with subcategories (expense / income) and active accounts for the operation form |
| `GET /api/operations?q=&kind=all\|expense\|income&account_id=&offset=&limit=` | history page (`total`, `next_offset`) |
| `POST /api/operations` | create: `kind` expense \| income (`currency`, `account_id`, `category`, `subcategory`) or transfer (`from_account_id`, `to_account_id`); `amount_minor`, `note`, `occurred_at` (`YYYY-MM-DDTHH:MM`, not in the future); answers the operation and `over_limit` |
| `GET / PUT / DELETE /api/operations/{id}` | read, edit (same fields; kind, currency and transfer accounts fixed), delete |
| `GET /api/report?period=week\|month\|year` | window, comparison window and per-currency (or combined UZS) sections |
| `GET /api/report/subcategories?period=&category=&currency=&converted=` | subcategories of one category |
| `GET /api/advice?period=` | `{"text": ...}` or `{"text": null, "reason": "not_configured" \| "no_data" \| "error"}` |
| `GET / PUT /api/settings` | `salary_day`, `rate_mode` auto \| manual (+ `rate`), `advice_weekly`, `advice_monthly`, `lang`; a PUT is checked as a whole before anything is saved |
| `GET / PUT / DELETE /api/budgets` | list with usage; set (`category`, `currency`, `amount_minor`); delete (`?category=`) |
| `GET / POST /api/accounts`, `GET / PUT / DELETE /api/accounts/{id}` | the cards screens (`deleted` or `archived`) |

`GET /` serves the page, `GET /healthz` answers `ok`.

### Environment variables (`.env`)

| Variable       | Description                                                              |
|----------------|--------------------------------------------------------------------------|
| `BOT_TOKEN`    | Token from [@BotFather](https://t.me/BotFather)                          |
| `ADMINS`       | Comma-separated Telegram user IDs allowed to use the bot                 |
| `ip`           | Host IP address (optional, unused with long polling)                     |
| `DATABASE_URL` | SQLAlchemy async URL, default `sqlite+aiosqlite:///./finora.db`          |
| `AI_PROVIDER` | `gemini` (default) or `claude`; voice input needs `gemini` |
| `GEMINI_API_KEY` | Google AI Studio key ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)); empty = AI off when the provider is `gemini` |
| `GEMINI_EXTRACT_MODEL` | Model for receipts, SMS, free text and voice, default `gemini-3.5-flash-lite` |
| `GEMINI_ANALYSIS_MODEL` | Model for Ask AI and advice, default `gemini-3.8-flash` |
| `GEMINI_TIMEOUT` | Seconds per extraction / voice request, default `60` |
| `GEMINI_ANALYSIS_TIMEOUT` | Seconds per Ask AI / advice request, default `180` |
| `ANTHROPIC_API_KEY` | Anthropic API key ([console.anthropic.com](https://console.anthropic.com/settings/keys)); empty = AI off when the provider is `claude` |
| `CLAUDE_EXTRACT_MODEL` | Model for receipts, SMS and free text, default `claude-haiku-5-5` |
| `CLAUDE_ANALYSIS_MODEL` | Model for Ask AI and advice, default `claude-opus-5-5` |
| `CLAUDE_TIMEOUT` | Seconds to wait for the extraction model, default `60`                   |
| `CLAUDE_ANALYSIS_TIMEOUT` | Seconds per Ask AI / advice request, default `180`              |
| `CLAUDE_REFUSAL_FALLBACK` | Retry a policy-declined Ask AI / advice request on Anthropic's recommended fallback model (server-side, beta), default `true` |
| `WEBAPP_URL` | Public `https://` address of the Mini App web server, e.g. `https://finance-ai-bot-production.up.railway.app`; empty (default) = no Mini App buttons (the chat then has no way to the reports and settings) |
| `PORT` | Port of the Mini App web server, default `8080` (Railway sets it) |

`.env` is gitignored, so your secrets are never committed. Copy `.env.example` to start.

### Deploy to Railway

The bot uses long polling (no webhook) and serves the Mini App over HTTP on `PORT` from the same process. It
runs on Railway as one service built from the `Dockerfile` (Python 3.11 with Chromium for the report cards). `railway.json` sets
the Dockerfile builder, restart on failure and exactly 1 replica.

> **Only one instance may poll a bot token.** Stop your local bot (and any other deployment using the
> same `BOT_TOKEN`) while Railway runs it, otherwise Telegram returns "Conflict: terminated by other
> getUpdates request". Never scale the service above 1 replica.

1. In Railway click **New Project -> Deploy from GitHub repo** and pick `aqoyliev/finance-ai-bot`.
2. Open the service, **Settings -> Volumes** (or `Ctrl+K` -> "Volume") and **add a Volume mounted at `/data`**.
   The SQLite file is stored there as `/data/finance.db`; without a volume the database is wiped on every deploy.
3. In **Variables** set:

   | Variable | Meaning |
   |----------|---------|
   | `BOT_TOKEN` | Token from @BotFather (required) |
   | `ADMINS` | Comma-separated Telegram user IDs allowed to use the bot (required) |
   | `DATABASE_URL` | Optional. The image defaults to `sqlite+aiosqlite:////data/finance.db` (four slashes = absolute path) |
   | `AI_PROVIDER` | `gemini` (default) or `claude`; voice input needs `gemini` |
   | `GEMINI_API_KEY` | Google AI Studio key; with `gemini` an empty key disables AI input, Ask AI and advice |
   | `GEMINI_EXTRACT_MODEL` | Model for receipts, SMS, free text, voice (default `gemini-3.5-flash-lite`) |
   | `GEMINI_ANALYSIS_MODEL` | Model for Ask AI and advice (default `gemini-3.8-flash`) |
   | `GEMINI_TIMEOUT` / `GEMINI_ANALYSIS_TIMEOUT` | Request timeouts in seconds (defaults `60` / `180`) |
   | `ANTHROPIC_API_KEY` | Claude API key; with `claude` an empty key disables AI input, Ask AI and advice |
   | `CLAUDE_EXTRACT_MODEL` | Model for receipts, SMS, free text (default `claude-haiku-5-5`) |
   | `CLAUDE_ANALYSIS_MODEL` | Model for Ask AI and advice (default `claude-opus-5-5`) |
   | `CLAUDE_TIMEOUT` / `CLAUDE_ANALYSIS_TIMEOUT` | Request timeouts in seconds (defaults `60` / `180`) |
   | `CLAUDE_REFUSAL_FALLBACK` | Retry policy-declined analysis requests on a fallback model (default `true`) |
   | `WEBAPP_URL` | The service's public `https://` domain (Settings -> Networking -> Generate Domain), e.g. `https://finance-ai-bot-production.up.railway.app`; enables the Mini App buttons |
   | `PORT` | Set by Railway; the Mini App web server listens on it (default `8080`) |

4. **Deploy**, then open **Deployments -> View logs**. A healthy start shows the Alembic migration lines
   and then aiogram polling; admins also get the "bot started" message in Telegram.
5. Every push to the connected branch redeploys automatically. Migrations run on start-up.

`GET /healthz` answers `ok` and can be used as the healthcheck path. In @BotFather you may also register the same
URL as the bot's Mini App (Bot Settings -> Configure Mini App), but it is not required: the bot sets the menu button
itself.

Postgres would be an alternative to SQLite + Volume (add the Railway Postgres plugin and set
`DATABASE_URL=postgresql+asyncpg://...`, plus the `asyncpg` dependency). It is not implemented here.

### Run

Python 3.11 is used (see `Pipfile`).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # then set BOT_TOKEN and ADMINS
python app.py
```

### Database migrations

Migrations are managed with Alembic (`alembic.ini`, `migrations/`). The URL comes from `DATABASE_URL`.
The bot runs `alembic upgrade head` automatically on start-up, so a fresh database is created on first run.
To run them by hand (requires a valid `.env`):

```bash
alembic upgrade head                                  # apply all migrations
alembic revision --autogenerate -m "describe change"  # after editing utils/db_api/models.py
alembic downgrade -1                                  # roll back the last migration
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a temporary SQLite database and never touch `.env` values or your real database.
The Claude and Gemini SDKs are mocked, so no API key is needed and no requests are sent.
The Mini App API is tested with aiohttp's test client and dummy-signed initData (`tests/test_miniapp.py`,
`tests/test_miniapp_screens.py`).

## Project structure

```
.
├── app.py                 # Entry point (long polling)
├── loader.py              # Bot & Dispatcher initialization
├── data/
│   └── config.py          # Reads settings from .env
├── handlers/
│   ├── users/             # start, help, legacy (hints for old commands / keyboard), ai_input (AI input), ask_ai, echo
│   ├── groups/            # group chat handlers
│   ├── channels/          # channel post handlers
│   └── errors/            # global error handler
├── keyboards/
│   └── inline/            # language picker and the Mini App (Web App) buttons
├── middlewares/           # access (ADMINS only), language, throttling
├── states/                # FSM states
├── filters/               # custom filters
├── migrations/            # alembic migrations (0007: rate source)
├── webapp/                # Mini App page: index.html, app.css, app.js (no build step; Home, NewOp, History, Report, Settings, cards)
├── tests/                 # pytest suite (service layer, reports / alerts / charts, AI parsing with mocked Claude / Gemini clients)
└── utils/
    ├── ai/                # provider switch + extraction (core.py), clients (gemini.py, claude.py), validation (parser.py), Ask AI + advice (assistant.py, tools.py)
    ├── advice_scheduler.py # weekly / monthly advice (asyncio task)
    ├── charts.py          # matplotlib expense chart (PNG bytes)
    ├── db_api/            # database helpers (reports, budgets, alerts, operations, ...)
    ├── miniapp/           # Mini App web server (aiohttp), JSON API (api.py: auth + accounts, screens.py: the other screens), initData validation
    ├── misc/              # logging, throttling decorator
    ├── notify_admins.py   # start-up notification
    ├── rates.py           # default USD rate: Central Bank of Uzbekistan + market fallbacks (fetch chain, cache, background refresh)
    ├── notify_alerts.py   # sends limit alerts after operations are saved / edited
    └── set_bot_commands.py
```

## License

[MIT](LICENSE) — based on
[anvarnarz/aiogram-bot-template](https://github.com/anvarnarz/aiogram-bot-template).
