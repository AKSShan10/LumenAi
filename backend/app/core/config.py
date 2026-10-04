"""All settings come from environment variables. Never hard-code secrets."""
import os

APP_NAME = os.getenv("APP_NAME", "LumenAI")

# Database: PostgreSQL. Built from the same POSTGRES_* values that Docker Compose uses, so
# `docker compose up db` + the backend on your own computer (development mode) just works.
# Inside Docker, docker-compose.yml sets DATABASE_URL directly (host "db").
POSTGRES_USER = os.getenv("POSTGRES_USER", "recruit")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "recruit")
POSTGRES_DB = os.getenv("POSTGRES_DB", "recruit")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
DATABASE_URL = os.getenv("DATABASE_URL") or (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# ---------------- AI model ----------------
# LLM_PROVIDER:
#   gemini - Google Gemini (our choice). Only LLM_API_KEY is needed; the address is filled in below.
#   openai - OpenAI, or any other OpenAI-compatible service (then set LLM_BASE_URL too)
#   fake   - offline stand-in for tests and trying the app without a key
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or (GEMINI_BASE_URL if LLM_PROVIDER == "gemini" else None)
LLM_MODEL = os.getenv("LLM_MODEL") or ("gemini-3.5-flash" if LLM_PROVIDER == "gemini" else "gpt-4o-mini")
# Temperature is NOT sent unless you set it. Google asks to keep Gemini 3 models at their
# default (1.0); lower values can make them loop. Stable scores come from our Python maths instead.
LLM_TEMPERATURE = float(os.environ["LLM_TEMPERATURE"]) if os.getenv("LLM_TEMPERATURE") else None

# ---------------- Login (simple JWT) ----------------
# One shared interviewer passcode; candidates never log in, they use their private link.
INTERVIEWER_PASSCODE = os.getenv("INTERVIEWER_PASSCODE", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")          # signs our login tokens; any long random text
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "10"))
