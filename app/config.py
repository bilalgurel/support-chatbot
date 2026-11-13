"""All settings come from the environment (.env). Nothing is hard-coded in the app."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
BUSINESS_DIR = Path(os.getenv("BUSINESS_DIR", str(BASE_DIR / "business")))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()  # "gemini" or "anthropic"
LLM_MODEL = os.getenv("LLM_MODEL", "")
MAX_ANSWER_TOKENS = int(os.getenv("MAX_ANSWER_TOKENS", "1500"))

MAX_TOOL_STEPS = int(os.getenv("MAX_TOOL_STEPS", "4"))        # tool calls allowed per customer message
HISTORY_MESSAGES = int(os.getenv("HISTORY_MESSAGES", "20"))   # how much of the chat the bot remembers
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "12"))

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
