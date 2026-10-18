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
# Embeddings turn a text into numbers, so the search can find documents with a similar meaning (RAG).
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or (
    "gemini-embedding-001" if LLM_PROVIDER == "gemini" else "text-embedding-3-small")

# ---------------- Login (simple JWT) ----------------
# The interviewer's email and password are in the database (table app_user), not here.
# Candidates never log in, they use their private link.
SECRET_KEY = os.getenv("SECRET_KEY", "")          # signs our login tokens; any long random text
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "10"))

# ---------------- Log file ----------------
# Every API call, AI call and job post is written here (see core/logging_setup.py). Empty = terminal only.
LOG_FILE = os.getenv("LOG_FILE", "logs/lumenai.log")

# ---------------- CV files and Google Drive ----------------
# Downloaded and uploaded CVs are saved here (inside backend/ unless the path starts at the disk root).
# The folder holds real CVs: it is in .gitignore and must never be committed.
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
# DRIVE_PROVIDER:
#   google - read the job's Google Form (Forms API) and the CVs from Google Drive (needs the key file)
#   fake   - read a folder on this computer instead (tests, and demos without a Google account)
DRIVE_PROVIDER = os.getenv("DRIVE_PROVIDER", "google")
GOOGLE_DRIVE_KEY_FILE = os.getenv("GOOGLE_DRIVE_KEY_FILE", "secrets/google-drive.json")   # service-account key; never committed
DRIVE_FAKE_FOLDER = os.getenv("DRIVE_FAKE_FOLDER", "tests/fake_drive")

# ---------------- CV screening ----------------
# SCREENING_MODE:
#   background - every new CV is screened by the backend by itself, one after another (the normal app)
#   manual     - nothing runs by itself; "Screen all again" screens while you wait (tests)
SCREENING_MODE = os.getenv("SCREENING_MODE", "background")
# When the free Gemini key says "too many requests", the background screening waits this long and tries again.
SCREENING_RATE_LIMIT_WAIT = int(os.getenv("SCREENING_RATE_LIMIT_WAIT", "60"))

# ---------------- Job posts on Blogger (through the Blogger MCP server) ----------------
# BLOGGER_PROVIDER:
#   blogger - really publish on the blog (needs the four values below)
#   fake    - publish nothing and answer as if it worked (tests, and demos without a blog)
BLOGGER_PROVIDER = os.getenv("BLOGGER_PROVIDER", "blogger")
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "")                # the number in the blog's address on blogger.com
BLOGGER_CLIENT_ID = os.getenv("BLOGGER_CLIENT_ID", "")            # from Google Cloud Console (OAuth client)
BLOGGER_CLIENT_SECRET = os.getenv("BLOGGER_CLIENT_SECRET", "")    # keep it only in .env
BLOGGER_REFRESH_TOKEN = os.getenv("BLOGGER_REFRESH_TOKEN", "")    # made once by scripts/blogger_login.py; only in .env
BLOGGER_API_URL = os.getenv("BLOGGER_API_URL", "https://www.googleapis.com/blogger/v3")
GOOGLE_TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")

# ---------------- Interview invitation (email with a calendar invite) ----------------
# The start of the candidate's private join link: APP_URL/join/<join_token>. Use the address candidates can open.
APP_URL = os.getenv("APP_URL", "http://localhost:8090").rstrip("/")
# SMTP sends the email, for example Gmail: host smtp.gmail.com, port 587, your address, an app password.
# SMTP_HOST empty = nothing is sent: the invitation is saved as "not sent" and can be copied by hand.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))                     # 587 = STARTTLS, 465 = SSL
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")                    # keep it only in .env
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER               # the sender address the candidate sees
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() != "false"

# ---------------- MCP servers ----------------
# Empty (default): the backend starts each MCP server itself as a short-lived child process (stdio).
# Docker: each server is its own service and these are their addresses (docker-compose.yml sets them).
MCP_BLOGGER_URL = os.getenv("MCP_BLOGGER_URL", "")                # http://blogger-mcp:8002/mcp
MCP_RECRUITMENT_URL = os.getenv("MCP_RECRUITMENT_URL", "")        # http://recruitment-mcp:8003/mcp

# ---------------- Video call (LiveKit) ----------------
# A LiveKit Cloud project (the free plan is enough): Settings > Keys. The secret signs the call tickets; keep it in .env.
# Empty = everything works except the video itself (the page says "Video is not set up").
# "/" = the LiveKit server in Docker, reached through the same address as the app (nginx passes /rtc to it).
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")                        # wss://your-project.livekit.cloud, or /
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

# ---------------- Live transcript (speech-to-text) ----------------
# STT_PROVIDER:
#   deepgram = Deepgram live (https://console.deepgram.com > API Keys); the key stays in .env
#   fake     = no service: test sentences (tests and demos without a key). Never use it for a real interview.
STT_PROVIDER = os.getenv("STT_PROVIDER", "deepgram")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-3")
DEEPGRAM_LANGUAGE = os.getenv("DEEPGRAM_LANGUAGE", "en")
DEEPGRAM_URL = os.getenv("DEEPGRAM_URL", "wss://api.deepgram.com/v1/listen")

# ---------------- Assessment (F6) ----------------
# Overall score = CV score x ASSESSMENT_CV_WEIGHT % + interview score x (100 - ASSESSMENT_CV_WEIGHT) %
ASSESSMENT_CV_WEIGHT = max(0, min(100, int(os.getenv("ASSESSMENT_CV_WEIGHT", "40"))))
