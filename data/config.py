from environs import Env

# Use the environs library
env = Env()
env.read_env()

# Read the following from the .env file
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot token
ADMINS = env.list("ADMINS")  # List of admins
IP = env.str("ip")  # Hosting IP address

# --- Finora features ---
OPENAI_API_KEY = env.str("OPENAI_API_KEY", default="")  # OpenAI API key for AI parsing
DATABASE_URL = env.str("DATABASE_URL", default="sqlite+aiosqlite:///./finora.db")  # SQLAlchemy async DB URL
WEBAPP_URL = env.str("WEBAPP_URL", default="http://localhost:8000")  # Mini App backend base URL
