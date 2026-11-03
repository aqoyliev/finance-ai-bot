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
- 📊 Report for the current financial month (it starts on the salary day, `/salaryday 5`)
- 🤖 AI input: record operations without menus from a receipt photo, a forwarded bank SMS
  or free text (see below)

All texts live in `utils/i18n.py`; operations are written through `record_operation` / `record_transfer`
in `utils/db_api/operations.py`.

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

### Environment variables (`.env`)

| Variable       | Description                                                              |
|----------------|--------------------------------------------------------------------------|
| `BOT_TOKEN`    | Token from [@BotFather](https://t.me/BotFather)                          |
| `ADMINS`       | Comma-separated Telegram user IDs allowed to use the bot                 |
| `ip`           | Host IP address (used for deployment / webhooks)                         |
| `DATABASE_URL` | SQLAlchemy async URL, default `sqlite+aiosqlite:///./finora.db`          |
| `ANTHROPIC_API_KEY` | Anthropic API key ([console.anthropic.com](https://console.anthropic.com/settings/keys)); empty = AI input off |
| `CLAUDE_EXTRACT_MODEL` | Model for receipts, SMS and free text, default `claude-haiku-5-5` |
| `CLAUDE_ANALYSIS_MODEL` | Model reserved for Q&A / advice (later phase), default `claude-opus-5-5` |
| `CLAUDE_TIMEOUT` | Seconds to wait for Claude, default `60`                               |

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
│   ├── users/             # start, help, menus, ai_input (AI drafts), echo fallback
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
├── tests/                 # pytest suite (service layer, AI parsing with a mocked Claude client)
└── utils/
    ├── ai/                # Claude client + prompt/schema (claude.py), validation (parser.py)
    ├── db_api/            # database helpers
    ├── misc/              # logging, throttling decorator
    ├── notify_admins.py   # start-up notification
    └── set_bot_commands.py
```

## License

[MIT](LICENSE) — based on
[anvarnarz/aiogram-bot-template](https://github.com/anvarnarz/aiogram-bot-template).
