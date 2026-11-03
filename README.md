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
  Settings. Starter accounts and categories are created once, in the language picked first
- ➖ Expenses / ➕ incomes by category and subcategory; a purchase can be split across several accounts
- 💳 Accounts (cash, debit, credit; UZS or USD): add, rename, change the opening balance or credit limit,
  deactivate (soft delete, history is kept). Credit cards show debt, limit and available credit
- 🔁 Transfers between own accounts of the same currency; a transfer to a credit card repays its debt.
  Transfers are never counted as income or expense
- ⚠️ Warning when an expense pushes a credit card's debt above its limit
- 🧾 History: open a recent operation to change its amount, category or account, or delete it
  (balances are recalculated; deleting a transfer removes both legs)
- 📊 Report for the financial month (it starts on the salary day, `/salaryday 5`): income, expenses and balance per
  currency, expenses by category with share and change versus the previous period, a donut chart (see below)
- 🎯 Monthly budgets per expense category and 🔔 alerts at 80% / 100% of a budget or of a credit card limit
- 🤖 AI input: record operations without menus from a receipt photo, a forwarded bank SMS
  or free text (see below)
- 💬 Ask AI: questions about your own data in plain language, plus 📅 weekly and 📆 monthly AI advice

All texts live in `utils/i18n.py`; operations are written through `record_operation` / `record_transfer`
in `utils/db_api/operations.py`.

### Category report and chart

📊 REPORT shows the current financial period as a chart (photo) with the text summary as its caption; when the text
does not fit Telegram's 1024-character caption limit it is sent as a separate message right after the photo.

- Per currency: income, expenses, balance (transfers are never counted), then expenses by category, biggest first,
  with the share of the total and the change versus the previous period. USD and UZS are shown separately; if a
  rate is set (`/rate 1 USD 12700 UZS`) an approximate combined total in UZS is added and the chart sums both in UZS.
- **Comparison rule:** while the period is still running it is compared with the *same number of days* from the
  start of the previous period (day 10 of this month vs days 1-10 of the last one); a finished period is
  compared with the whole previous one. The note under the report shows the compared dates.
- Tap a category for its subcategory breakdown; ◀ / ▶ move to the previous / next period (never into the future);
  the account balances are on 💳 ACCOUNTS.
- The chart is a donut for up to 8 categories (tiny slices merged into "Other"), horizontal bars for more (top 9 +
  "Other"). It is drawn by matplotlib (Agg backend, DejaVu Sans font, so Cyrillic and Uzbek letters render; emoji in
  category names are dropped from the chart labels) in a worker thread. If drawing fails, or there are no
  expenses, the report is sent as text only. With expenses in both currencies and no rate, only the first
  currency (UZS) is charted.

### Budgets and alerts

Settings → 🎯 Budgets: pick an expense category, then set, change or remove its monthly limit (UZS or USD; the month
is the financial period). The report shows `spent / limit`, the percentage and a progress bar for every budget.
Spending in the other currency counts towards a budget when a USD rate is set.

After an expense is saved (manually or from an AI draft), edited (amount, category or account) or after a
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

### AI input (Anthropic Claude)

Send the bot any of these instead of using the menu:

- a **receipt photo** (or an image / PDF sent as a file; JPEG, PNG, GIF, WebP, up to 5 MB, PDF up to 15 MB); the total paid is used, not the individual lines
- **free text** in Uzbek, Russian or English: `taksi 25000 uob kartadan`, `кофе 18 тысяч наличными`,
  `got salary 12m to hamkorbank`; several operations in one message are fine
- a **forwarded / pasted bank SMS** or notification (Uzcard, Humo, Visa; debit and credit)

The bot shows a draft card (amount, type, category, account, date, note). Nothing is saved until you press
✅ Save; ✏️ buttons change the amount, category, account, type, currency or date, ❌ Cancel drops it. Missing
required fields (e.g. the account) must be filled in first. Several drafts from one message are confirmed one
by one (⏭ Skip) or with ✅ Save all. The card warns when an almost identical operation already exists (same
amount and account within 10 minutes, or the same SMS / photo sent again). Saved rows have `source = "ai"`.

Voice messages are not supported (Claude has no audio input); the bot replies that you should send text or a photo.

How it works: `utils/ai/claude.py` sends the input (image/PDF bytes inline, no separate OCR) plus a list of
your accounts and categories to the Claude API (`claude-haiku-5-5` by default) and asks for JSON that follows
a fixed schema (structured outputs, `output_config.format`).
`utils/ai/parser.py` never trusts the answer: amounts are re-parsed (`125 000,00`, `125.000`, `18 ming`, `12m`),
the currency must be UZS/USD, the account must be yours and in that currency, the category must exist;
anything doubtful is left empty for you to choose. Card digits from an SMS (`*1234`) match an account whose
**name contains those 4 digits**, e.g. rename the account to `UOB 1234`.

While you are inside a menu step (e.g. typing an amount), text goes to that step, not to the AI.
Without `ANTHROPIC_API_KEY` the bot works as before and answers that AI input is not configured.

> **Privacy:** receipts and texts you send for AI input, together with the names of your accounts and
> categories, are sent to Anthropic (Claude API) for processing. Balances and history are not sent.

### Ask AI and automatic advice

**Ask AI.** Press 🤖 ASK AI in the main menu and type questions ("how much did I spend on taxi this month?",
"am I spending more than last month?", "how much credit is left?"). The bot stays in this mode, so follow-up
questions work ("and last month?"), until you press 🏠 Menu. You can also just type a question without the
button: the extraction model classifies every free-text message as an *operation*, a *question* or *other*;
questions go to Ask AI, operations still become drafts. Photos, files and bank SMS always go to AI input.

How it works (`utils/ai/assistant.py`, `utils/ai/tools.py`): the analysis model (`claude-opus-5-5`) gets
read-only **client-side tools** backed by the service layer instead of a database dump:
`get_period_summary`, `get_category_breakdown`, `search_transactions`, `get_accounts`, `get_budgets`,
`get_categories`, `get_exchange_rate` (strict JSON schemas; results are compact JSON with amounts and
currency; transfers are never income or expense). The bot runs the tool loop itself (at most 6 model requests
and 4 minutes per question) and answers in your language as plain text. The conversation is kept in memory
(FSM) for an hour; after 6 questions it is compacted to the last 3 question/answer pairs.

**Advice.** 📅 a weekly summary every **Monday at 09:00** (Tashkent time): the last 7 days vs the 7 before,
top categories, unusual spending, budget status and 2-4 saving tips. 📆 A monthly review at **09:00 on the
first day of a new financial month** (your salary day): the finished period vs the one before, budgets,
credit cards and advice for the new period. Turn either off in ⚙️ Settings → 🤖 AI advice; 💡 Get advice now
(in Ask AI, the report and the advice settings) reviews the running period on demand. Nothing is sent for a
window without income or expenses.
The scheduler (`utils/advice_scheduler.py`) is an asyncio task started in `on_startup` that checks once a
minute; what was sent is stored on the user row (migration `0004`), so a restart never sends twice and advice
missed while the bot was down at 09:00 is sent on the next start the same day. The model gets pre-computed
summaries, not raw rows.

> **Privacy:** your questions, the data the assistant looks up to answer them (totals, categories,
> matching operations, balances) and the summaries used for advice are sent to Anthropic (Claude API).

### Environment variables (`.env`)

| Variable       | Description                                                              |
|----------------|--------------------------------------------------------------------------|
| `BOT_TOKEN`    | Token from [@BotFather](https://t.me/BotFather)                          |
| `ADMINS`       | Comma-separated Telegram user IDs allowed to use the bot                 |
| `ip`           | Host IP address (used for deployment / webhooks)                         |
| `DATABASE_URL` | SQLAlchemy async URL, default `sqlite+aiosqlite:///./finora.db`          |
| `ANTHROPIC_API_KEY` | Anthropic API key ([console.anthropic.com](https://console.anthropic.com/settings/keys)); empty = AI input off |
| `CLAUDE_EXTRACT_MODEL` | Model for receipts, SMS and free text, default `claude-haiku-5-5` |
| `CLAUDE_ANALYSIS_MODEL` | Model for Ask AI and advice, default `claude-opus-5-5` |
| `CLAUDE_TIMEOUT` | Seconds to wait for the extraction model, default `60`                   |
| `CLAUDE_ANALYSIS_TIMEOUT` | Seconds per Ask AI / advice request, default `180`              |
| `CLAUDE_REFUSAL_FALLBACK` | Retry a policy-declined Ask AI / advice request on Anthropic's recommended fallback model (server-side, beta), default `true` |

`.env` is gitignored, so your secrets are never committed. Copy `.env.example` to start.

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
The Claude client is mocked, so no API key is needed and no requests are sent.

## Project structure

```
.
├── app.py                 # Entry point (long polling)
├── loader.py              # Bot & Dispatcher initialization
├── data/
│   └── config.py          # Reads settings from .env
├── handlers/
│   ├── users/             # start, help, menus, reports, budgets, ai_input (AI drafts), ask_ai, advice, echo
│   ├── groups/            # group chat handlers
│   ├── channels/          # channel post handlers
│   └── errors/            # global error handler
├── keyboards/
│   ├── default/           # reply keyboards
│   └── inline/            # inline keyboards
├── middlewares/           # access (ADMINS only), language, throttling
├── states/                # FSM states
├── filters/               # custom filters
├── migrations/            # alembic migrations
├── tests/                 # pytest suite (service layer, reports / alerts / charts, AI parsing with a mocked Claude client)
└── utils/
    ├── ai/                # Claude client (claude.py), validation (parser.py), Ask AI + advice (assistant.py, tools.py)
    ├── advice_scheduler.py # weekly / monthly advice (asyncio task)
    ├── charts.py          # matplotlib expense chart (PNG bytes)
    ├── db_api/            # database helpers (reports, budgets, alerts, operations, ...)
    ├── misc/              # logging, throttling decorator
    ├── notify_admins.py   # start-up notification
    ├── notify_alerts.py   # sends limit alerts after operations are saved / edited
    └── set_bot_commands.py
```

## License

[MIT](LICENSE) — based on
[anvarnarz/aiogram-bot-template](https://github.com/anvarnarz/aiogram-bot-template).
