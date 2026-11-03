from environs import Env

# Use the environs library
env = Env()
env.read_env()

# Read the following from the .env file
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot token
ADMINS = env.list("ADMINS")  # List of admins
IP = env.str("ip")  # Hosting IP address

# --- Finora features ---
DATABASE_URL = env.str("DATABASE_URL", default="sqlite+aiosqlite:///./finora.db")  # SQLAlchemy async DB URL
WEBAPP_URL = env.str("WEBAPP_URL", default="http://localhost:8000")  # Mini App backend base URL

# --- AI input (Anthropic Claude API) ---
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="")  # empty = AI input disabled
CLAUDE_EXTRACT_MODEL = env.str("CLAUDE_EXTRACT_MODEL", default="claude-haiku-5-5")  # receipts, SMS, free text
CLAUDE_ANALYSIS_MODEL = env.str("CLAUDE_ANALYSIS_MODEL", default="claude-opus-5-5")  # reserved: Q&A, advice
CLAUDE_TIMEOUT = env.int("CLAUDE_TIMEOUT", default=60)  # seconds per request
