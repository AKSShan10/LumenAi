"""Where the log lines go: the terminal, and a log file that is kept after a restart.

The file holds what happened and how it ended, so the status of the work can be checked later:

    2026-10-06 12:33:57 INFO api: POST /api/jobs/7/post 200 1840ms          every API call
    2026-10-06 12:33:55 INFO llm: AI call ok model=gemini-3.5-flash 2.1s    every call to the AI service
    2026-10-06 12:33:57 INFO job_posting: blogger post job=7 posted         every job post

Privacy: a line has the address, ids, the result and the time taken. It never has what was typed or
uploaded (no passcode, no CV text, no names), and never the text after "?" in an address.

LOG_FILE in .env chooses the file (default backend/logs/lumenai.log). Empty = terminal only.
One file for the whole app: the backend and the two MCP servers (their own Docker services) write to the same file.
Only the backend starts a new file at 1 MB (rotate=True); the MCP servers follow the file when it is renamed.
LOG_TIME_ZONE in .env chooses the time shown in each line (default Asia/Dhaka, Bangladesh time). A Docker container
runs on UTC, so without this the log would be 6 hours behind Bangladesh time. The database still keeps UTC.
When the file reaches 1 MB a new one is started; the 5 newest old files are kept (lumenai.log.1 ... lumenai.log.5).
"""
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler, WatchedFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
BACKEND_DIR = Path(__file__).resolve().parents[2]
MAX_BYTES = 1_000_000
OLD_FILES_KEPT = 5


# Makes every log line show its time in this time zone (an unknown name keeps the computer's own time)
def use_time_zone(name: str) -> None:
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logging.getLogger("app").warning("LOG_TIME_ZONE %r is not known; the log keeps the computer's time", name)
        return
    # the log turns each line's time (seconds) into a date and time with this function
    # (staticmethod: the log calls it as formatter.converter(seconds), without the formatter itself)
    logging.Formatter.converter = staticmethod(lambda seconds: datetime.fromtimestamp(seconds, zone).timetuple())


# Sends log lines to the terminal and to the log file (LOG_FILE); called once in main.py and in each MCP server.
# rotate=True: this program starts a new file at 1 MB (the backend). rotate=False: it only adds lines and opens the
# file again when the backend has renamed it (the MCP servers), so two programs never rotate the same file.
def setup_logging(log_file: str, time_zone: str = "", rotate: bool = True) -> None:
    if time_zone:
        use_time_zone(time_zone)
    logging.basicConfig(level=logging.INFO, format=FORMAT)          # the terminal
    # The web client library would log the full address of every outside call. An address can hold a
    # secret (a token can be part of it), so only its warnings and errors are kept.
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # The MCP library writes a line for every session and request ("Created new transport ..."); only its problems
    # are kept, so the file shows what the app did, not the plumbing.
    logging.getLogger("mcp").setLevel(logging.WARNING)
    if not log_file:
        return
    path = Path(log_file)
    if not path.is_absolute():
        path = BACKEND_DIR / path                                    # "logs/lumenai.log" -> backend/logs/lumenai.log
    root = logging.getLogger()
    if any(getattr(handler, "baseFilename", "") == str(path) for handler in root.handlers):
        return                                                       # already set up (the app was loaded twice)
    path.parent.mkdir(parents=True, exist_ok=True)
    if rotate:
        file_handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=OLD_FILES_KEPT, encoding="utf-8")
    else:
        file_handler = WatchedFileHandler(path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)
