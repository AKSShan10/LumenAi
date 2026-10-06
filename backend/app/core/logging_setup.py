"""Where the log lines go: the terminal, and a log file that is kept after a restart.

The file holds what happened and how it ended, so the status of the work can be checked later:

    2026-10-06 12:33:57 INFO api: POST /api/jobs/7/post 200 1840ms          every API call
    2026-10-06 12:33:55 INFO llm: AI call ok model=gemini-3.5-flash 2.1s    every call to the AI service
    2026-10-06 12:33:57 INFO job_posting: telegram post job=7 posted        every Telegram post

Privacy: a line has the address, ids, the result and the time taken. It never has what was typed or
uploaded (no passcode, no CV text, no names), and never the text after "?" in an address.

LOG_FILE in .env chooses the file (default backend/logs/lumenai.log). Empty = terminal only.
When the file reaches 1 MB a new one is started; the 5 newest old files are kept (lumenai.log.1 ... lumenai.log.5).
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
BACKEND_DIR = Path(__file__).resolve().parents[2]
MAX_BYTES = 1_000_000
OLD_FILES_KEPT = 5


def setup_logging(log_file: str) -> None:
    logging.basicConfig(level=logging.INFO, format=FORMAT)          # the terminal
    # The web client library would log the full address of every outside call. An address can hold a
    # secret (the Telegram bot token is part of it), so only its warnings and errors are kept.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not log_file:
        return
    path = Path(log_file)
    if not path.is_absolute():
        path = BACKEND_DIR / path                                    # "logs/lumenai.log" -> backend/logs/lumenai.log
    root = logging.getLogger()
    if any(getattr(handler, "baseFilename", "") == str(path) for handler in root.handlers):
        return                                                       # already set up (the app was loaded twice)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=OLD_FILES_KEPT, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)
