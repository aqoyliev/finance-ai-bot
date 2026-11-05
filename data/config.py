from environs import Env

# Use the environs library
env = Env()
env.read_env()

# Read the following from the .env file
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot token
ADMINS = env.list("ADMINS")  # Owners: full access, manage users, never shown in any user list
ADMIN_IDS = frozenset(int(admin) for admin in ADMINS if str(admin).strip().isdigit())  # owner ids
# Superadmins: use the bot and add / remove users in the Mini App; fixed here, not shown in the users list
SUPERADMINS = env.list("SUPERADMINS", default=[])
SUPERADMIN_IDS = frozenset(int(x) for x in SUPERADMINS if str(x).strip().isdigit()) - ADMIN_IDS
# Everybody else needs a grant stored in the database (utils/db_api/access.py)
IP = env.str("ip", default="")  # Hosting IP address (unused with long polling; optional)

# --- Finora features ---
DATABASE_URL = env.str("DATABASE_URL", default="sqlite+aiosqlite:///./finora.db")  # SQLAlchemy async DB URL
# Mini App: public HTTPS address of the web server below (e.g. https://<app>.up.railway.app).
# Empty = the server still runs, but the bot shows no Mini App buttons (Telegram only opens https:// Mini Apps).
WEBAPP_URL = env.str("WEBAPP_URL", default="").strip()
WEBAPP_HOST = env.str("WEBAPP_HOST", default="0.0.0.0")  # interface the Mini App web server listens on
PORT = env.int("PORT", default=8080)  # Mini App web server port (Railway sets PORT)
# Mini App buttons are shown only for an https:// URL: Telegram rejects any other web_app button
WEBAPP_ENABLED = WEBAPP_URL.lower().startswith("https://")

# --- AI provider: "gemini" (Google Gemini, default; also reads voice messages) or "claude" (Anthropic) ---
AI_PROVIDER = env.str("AI_PROVIDER", default="gemini").strip().lower()
if AI_PROVIDER not in ("gemini", "claude"):
    raise ValueError(f"AI_PROVIDER must be 'gemini' or 'claude', not {AI_PROVIDER!r}")

# --- Google Gemini (Google AI Studio key) ---
GEMINI_API_KEY = env.str("GEMINI_API_KEY", default="")  # empty = AI disabled when AI_PROVIDER=gemini
GEMINI_EXTRACT_MODEL = env.str("GEMINI_EXTRACT_MODEL", default="gemini-3.5-flash-lite")  # receipts, SMS, voice
GEMINI_ANALYSIS_MODEL = env.str("GEMINI_ANALYSIS_MODEL", default="gemini-3.8-flash")  # Ask AI, advice
GEMINI_TIMEOUT = env.int("GEMINI_TIMEOUT", default=60)  # seconds per extraction / voice request
GEMINI_ANALYSIS_TIMEOUT = env.int("GEMINI_ANALYSIS_TIMEOUT", default=180)  # seconds per Ask AI / advice request

# --- Anthropic Claude API ---
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="")  # empty = AI disabled when AI_PROVIDER=claude
CLAUDE_EXTRACT_MODEL = env.str("CLAUDE_EXTRACT_MODEL", default="claude-haiku-5-5")  # receipts, SMS, free text
CLAUDE_ANALYSIS_MODEL = env.str("CLAUDE_ANALYSIS_MODEL", default="claude-opus-5-5")  # Ask AI, advice
CLAUDE_TIMEOUT = env.int("CLAUDE_TIMEOUT", default=60)  # seconds per extraction request
CLAUDE_ANALYSIS_TIMEOUT = env.int("CLAUDE_ANALYSIS_TIMEOUT", default=180)  # seconds per Ask AI / advice request
# Retry a policy-declined analysis request on Anthropic's recommended fallback model (server-side, beta)
CLAUDE_REFUSAL_FALLBACK = env.bool("CLAUDE_REFUSAL_FALLBACK", default=True)
