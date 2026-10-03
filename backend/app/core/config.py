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
