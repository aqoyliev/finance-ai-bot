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

- 🔐 Private: only Telegram IDs listed in `ADMINS` can use it; anyone else gets one short "private bot" reply
- 🌐 Uzbek (Latin), Russian and English. The language is chosen on the first `/start` and can be changed in
  Settings. Starter categories and one account, Cash (UZS), are created once, in the language picked first; the
  user adds their own cards in ⚙️ Settings → Accounts
- ✍️ Operations are added by typing or speaking (see AI input below) and saved at once; `/expense`, `/income` and
  `/transfer` remain for manual entry (a purchase can be split across several accounts there)
- ⌨️ A small reply keyboard instead of a menu: 📊 Report, 💳 Balance, ⚙️ Settings (accounts, budgets, history,
  AI advice, language); it is shown after the language choice and on every `/start`, and also attached to the
  "no operation found" reply and to saved-operation cards, so users who never re-ran `/start` get it. The buttons
  also work as plain words in any language, any case, with or without the emoji (`settings`, `sozlamalar`,
  `настройки`, `report`, `hisobot`, `отчет`, `balance`, `balans`, `баланс`), and `/settings`, `/report` and
  `/balance` open the same screens
- 🧾 Every saved operation is confirmed with a short card (see below)
- 💳 Accounts (cash, debit, credit; UZS or USD): add, rename, change the opening balance or credit limit,
  deactivate (soft delete, history is kept). Credit cards show debt, limit and available credit
- 📱 A Telegram Mini App for the cards (see Mini App below): balances, add / edit / delete, the month's totals and the
  last operations of a card
- 🔁 Transfers between own accounts of the same currency; a transfer to a credit card repays its debt.
  Transfers are never counted as income or expense
- ⚠️ Warning when an expense pushes a credit card's debt above its limit
- 🧾 History (⚙️ Settings → 🧾 History): open a recent operation to change its amount, category or account, or
  delete it (balances are recalculated; deleting a transfer removes both legs)
- 📊 Report for the financial month (it starts on the salary day, `/salaryday 5`): income, expenses and balance per
  currency, expenses by category with share and change versus the previous period, a donut chart (see below)
- 🎯 Monthly budgets per expense category and 🔔 alerts at 80% / 100% of a budget or of a credit card limit
- 🤖 AI input: record operations from free text, a voice message, a receipt photo or a forwarded bank SMS,
  without confirmation (see below)
- 💬 Ask AI: type a question about your own data in plain language; plus 📅 weekly and 📆 monthly AI advice

All texts live in `utils/i18n.py`; operations are written through `record_operation` / `record_transfer`
in `utils/db_api/operations.py`.

### Category report and chart

📊 Report (reply keyboard) shows the current financial period as a chart (photo) with the text summary as its caption; when the text
does not fit Telegram's 1024-character caption limit it is sent as a separate message right after the photo.

- Per currency: income, expenses, balance (transfers are never counted), then expenses by category, biggest first,
  with the share of the total and the change versus the previous period. USD and UZS are shown separately; if a
  rate is set (`/rate 1 USD 12700 UZS`) an approximate combined total in UZS is added and the chart sums both in UZS.
- **Comparison rule:** while the period is still running it is compared with the *same number of days* from the
  start of the previous period (day 10 of this month vs days 1-10 of the last one); a finished period is
  compared with the whole previous one. The note under the report shows the compared dates.
- Tap a category for its subcategory breakdown; ◀ / ▶ move to the previous / next period (never into the future);
  the account balances are on 💳 Balance.
- The image is a receipt-style card (see below). Only if the card cannot be rendered, the old matplotlib chart is
  sent instead: a donut for up to 8 categories (tiny slices merged into "Other"), horizontal bars for more (top 9 +
  "Other"), DejaVu Sans, drawn in a worker thread (`utils/charts.py`). If that fails too, the report is text only.

### Receipt cards

The report image and the weekly / monthly advice come as receipt cards (`utils/cards.py`, templates in
`templates/cards/`): Jinja2 HTML rendered to a 1080 px wide PNG (height follows the content) by headless Chromium
through Playwright. The JetBrains Mono font is vendored in `assets/fonts/` (SIL OFL, `OFL.txt`) and embedded into
the page, so rendering works offline.

- **Weekly receipt** (with the Monday advice): categories with the change vs the previous week, total, a 7-day
  barcode (biggest day in red), the biggest single expense with its weekday and the most-used budget.
- **Monthly receipt** (with the advice on the salary day, for the period that just ended): up to 8 categories (the
  rest folded into "Other"), total vs the previous period, income / expenses / balance, a barcode per 7 days, top 3
  expenses, budgets as `[#######---]` bars and the payment method split (cash / debit / credit card) with credit
  limit use.
- **Report** (📊 Report, any period; also with "Get advice now"): categories with share bars and change, total vs the
  previous period (or its same days), over-budget categories.
- No expenses in the window: an "empty" receipt. Expenses in both UZS and USD: one section per currency, never
  converted.

The stamp shows the change of total spending (▲ red = spent more, ▼ blue = less). The advice text is the photo's
caption when it fits 1024 characters, otherwise the photo is followed by the text as a message.

One Chromium is started lazily on the first card, reused (at most 2 pages at a time) and closed on shutdown. If
Playwright or Chromium is missing, crashes or a card takes longer than 25 s, the problem is logged and the bot falls
back to the matplotlib chart, then to text; a failed browser start is retried after 5 minutes.

Setup: `pip install -r requirements.txt`, then `python -m playwright install chromium`. In Docker use
`playwright install --with-deps chromium` (it also installs the system libraries Chromium needs).

### Budgets and alerts

Settings → 🎯 Budgets: pick an expense category, then set, change or remove its monthly limit (UZS or USD; the month
is the financial period). The report shows `spent / limit`, the percentage and a progress bar for every budget.
Spending in the other currency counts towards a budget when a USD rate is set.

After an expense is saved (manually or from AI input), edited (amount, category or account) or after a
transfer touches a credit card, the bot checks the budgets of the affected categories and the affected credit cards
and sends **one message per threshold (80% and 100%) per period** for each category / card:

- sent alerts are stored in `alerts_sent` keyed by the period start, so every new period starts clean;
- deleting or lowering an expense does not "unsend" anything, and crossing a threshold again within the same
  period is not announced again;
- one change that jumps over both thresholds produces only the 100% alert;
- changing or removing a budget limit clears that category's alerts for a fresh start;
- the existing "debt above the limit" warning in the save confirmation stays; its card does not get a second
  100% message for the same save.

Checks run in one service, `db.check_alerts` (`utils/db_api/alerts.py`), called through
`utils/notify_alerts.send_alerts` from the handlers that save or edit operations.

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

Every saved operation (AI input, `/expense`, `/income`, `/transfer`) is confirmed with the same short HTML card
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
  answer applies to all of them. The last button, "➕ Add a new card", opens the add-account flow and the waiting
  operations are saved to the new card (if its currency does not fit, the question is asked again). Other typed
  text without digits gets a short hint ("pick a button or add a new card"); text with an operation in it is
  analyzed as usual. With only one account there is nothing to ask: the operation is saved to it.
- **Category.** An expense or income without a recognizable category goes to "Other" ("Boshqa" / "Прочее";
  "Other income" for incomes), created if the user has none.
- **Amount.** An operation without an amount is not saved; the bot answers that no amount was understood.
- A transfer whose receiving account is unclear is not saved; the bot points to `/transfer`.
- **Duplicates.** The same SMS, photo or file sent again is not saved twice ("already saved"). The same amount on
  the same account within 10 minutes (e.g. a typed taxi and then its bank SMS) is saved, with a warning that
  points to ⚙️ Settings → 🧾 History for deleting it. Typed text has no fingerprint, so writing "coffee 18000"
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

While you are inside a manual step (e.g. typing an amount after `/expense`), text goes to that step, not to the
AI. The reply-keyboard buttons are handled before everything else (`handlers/users/menu.py` is registered right
after `start`), so their texts never reach the AI or a form step, and pressing one ends any flow in progress.
Without the key of the selected provider the manual commands still work and free text gets an "AI input is not
configured" answer.

> **Privacy:** receipts and texts you send for AI input, together with the names of your accounts and
> categories, are sent to the selected AI provider (Google Gemini API or Anthropic Claude API) for
> processing. Balances and history are not sent.

### Ask AI and automatic advice

**Ask AI.** Just type a question ("how much did I spend on taxi this month?", "am I spending more than last
month?", "how much credit is left?"): the extraction model classifies every free-text message as an
*operation*, a *question* or *other*; questions go to Ask AI, operations are saved. Follow-up questions work
("and last month?") because the conversation is kept and the extraction model is told about it; `/start`, a
reply-keyboard button or a newly saved operation starts a fresh one. Photos, files and bank SMS always go to AI
input.

How it works (`utils/ai/assistant.py`, `utils/ai/tools.py`): the analysis model (`gemini-3.8-flash` or
`claude-opus-5-5`) gets
read-only **client-side tools** backed by the service layer instead of a database dump:
`get_period_summary`, `get_category_breakdown`, `search_transactions`, `get_accounts`, `get_budgets`,
`get_categories`, `get_exchange_rate` (strict JSON schemas; results are compact JSON with amounts and
currency; transfers are never income or expense; Gemini gets them as function declarations). The bot runs
the tool loop itself (at most 6 model requests
and 4 minutes per question) and answers in your language as plain text. The conversation is kept in memory
(FSM) for an hour; after 6 questions it is compacted to the last 3 question/answer pairs.

**Advice.** 📅 a weekly summary every **Monday at 09:00** (Tashkent time): the last 7 days vs the 7 before,
top categories, unusual spending, budget status and 2-4 saving tips. 📆 A monthly review at **09:00 on the
first day of a new financial month** (your salary day): the finished period vs the one before, budgets,
credit cards and advice for the new period. Turn either off in ⚙️ Settings → 🤖 AI advice; 💡 Get advice now
(in the report and the advice settings) reviews the running period on demand. Nothing is sent for a
window without income or expenses.
The scheduler (`utils/advice_scheduler.py`) is an asyncio task started in `on_startup` that checks once a
minute; what was sent is stored on the user row (migration `0004`), so a restart never sends twice and advice
missed while the bot was down at 09:00 is sent on the next start the same day. The model gets pre-computed
summaries, not raw rows.

> **Privacy:** your questions, the data the assistant looks up to answer them (totals, categories,
> matching operations, balances) and the summaries used for advice are sent to the selected AI provider.

### Mini App (cards)

A Telegram Mini App for managing accounts, served by the bot process itself: `on_startup` starts an aiohttp web
server on `PORT` (default `8080`, all interfaces) next to long polling and stops it on shutdown. The page is plain
HTML + CSS + JS in `webapp/` (no build step), drawn as paper receipts in JetBrains Mono (served from `assets/fonts/`,
no Google Fonts); the server code is in `utils/miniapp/`.

- **💳 Kartalarim:** total balance in UZS (plus USD when there are USD accounts), the number of accounts, every account
  with a type tag (NAQD / UZCARD / HUMO / VISA / MASTERCARD, KREDIT for credit cards), name, `•••• 1234` and
  balance; credit cards show the debt in red and the limit. "Karta qo'shish" opens the form.
- **Yangi karta / Tahrirlash:** type, name / bank, last 4 digits (exactly 4; optional for cash), currency, current
  balance and a "Kredit karta" box that turns the balance into the current debt and shows the credit limit. Only the
  last 4 digits are stored, never the card number; two active accounts cannot share them. The current balance works
  like the opening balance in the chat: editing it moves the opening balance by the difference, so history stays
  consistent. The currency of an account with operations cannot change.
- **Karta tafsiloti:** a stamp with the type, the balance (or debt), last 4 and currency, the expense and income of
  the current financial month (from the salary day) and the last 10 operations. Delete asks for confirmation: an
  account without operations is deleted, one with operations is archived (hidden, history kept), like
  "deactivate" in the chat.
- Texts are in uz / ru / en (`WEBAPP_TEXTS` in `utils/i18n.py`), in the language chosen in the bot. The Telegram Back
  button and the in-page buttons both work.

**Opening it.** With `WEBAPP_URL` set to the public `https://` address of the server, ⚙️ Settings → 💳 Accounts gets a
"💳 Kartalarim (Mini App)" button and each admin's chat menu button opens the Mini App (set at start-up; reset to the
default when `WEBAPP_URL` is empty). Without `WEBAPP_URL`, or with a non-https one, the server still runs but the bot
shows no Mini App buttons (Telegram only opens https Mini Apps). The "➕ Add a new card" button of the AI account
question still uses the chat flow.

**Security.** Every `/api/` request carries `Telegram.WebApp.initData` in the `X-Telegram-Init-Data` header. The server
checks its HMAC-SHA256 signature with the bot token (secret = `HMAC_SHA256("WebAppData", BOT_TOKEN)`), refuses data
older than 24 hours and takes the user id from it; only IDs in `ADMINS` get through (401 for missing / bad /
expired data, 403 for anyone else). initData and the token are never logged.

API (amounts are integers in minor units): `GET /api/me` (language and texts), `GET /api/accounts`,
`POST /api/accounts`, `GET /api/accounts/{id}` (with month totals and recent operations),
`PUT /api/accounts/{id}`, `DELETE /api/accounts/{id}` (`deleted` or `archived`). `GET /` serves the page,
`GET /healthz` answers `ok`.

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
| `WEBAPP_URL` | Public `https://` address of the Mini App web server, e.g. `https://finance-ai-bot-production.up.railway.app`; empty (default) = no Mini App buttons |
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

## Project structure

```
.
├── app.py                 # Entry point (long polling)
├── loader.py              # Bot & Dispatcher initialization
├── data/
│   └── config.py          # Reads settings from .env
├── handlers/
│   ├── users/             # start, menu (reply keyboard), help, settings, finance (/expense, /income, history), transfer, accounts, reports, budgets, operations, advice, ai_input (AI input), ask_ai, echo
│   ├── groups/            # group chat handlers
│   ├── channels/          # channel post handlers
│   └── errors/            # global error handler
├── keyboards/
│   ├── default/           # reply keyboard (📊 Report, 💳 Balance, ⚙️ Settings)
│   └── inline/            # inline keyboards
├── middlewares/           # access (ADMINS only), language, throttling
├── states/                # FSM states
├── filters/               # custom filters
├── migrations/            # alembic migrations
├── webapp/                # Mini App page: index.html, app.css, app.js (no build step)
├── tests/                 # pytest suite (service layer, reports / alerts / charts, AI parsing with mocked Claude / Gemini clients)
└── utils/
    ├── ai/                # provider switch + extraction (core.py), clients (gemini.py, claude.py), validation (parser.py), Ask AI + advice (assistant.py, tools.py)
    ├── advice_scheduler.py # weekly / monthly advice (asyncio task)
    ├── charts.py          # matplotlib expense chart (PNG bytes)
    ├── db_api/            # database helpers (reports, budgets, alerts, operations, ...)
    ├── miniapp/           # Mini App web server (aiohttp), JSON API, initData validation
    ├── misc/              # logging, throttling decorator
    ├── notify_admins.py   # start-up notification
    ├── notify_alerts.py   # sends limit alerts after operations are saved / edited
    └── set_bot_commands.py
```

## License

[MIT](LICENSE) — based on
[anvarnarz/aiogram-bot-template](https://github.com/anvarnarz/aiogram-bot-template).
