"""The backend screens CVs by itself, in the background, and keeps track of the progress for the page.

    start_screening(job_id)      called when CVs are saved (Google Form fetch, manual upload) or "Screen all again"
    screen_waiting(job_id)       screens every CV of the job that waits, one after another, and counts the progress
    progress_of(job_id)          {running, total, done, included, excluded, needs_review, finished_at} for the page
    resume_waiting_screening()   after a restart: screens what was still waiting (registered in main.py)

One background thread works through a queue of jobs. The web request that saved the CVs does not wait for this, so the
60 second limit of the web server does not matter. The page asks progress_of() every few seconds and shows
"Screening 3 of 7 CVs" with a progress bar, then "Screening finished: 4 included, 3 excluded".

The free Gemini key allows only a few requests per minute. When a CV comes back with "too many requests", the
thread waits SCREENING_RATE_LIMIT_WAIT seconds and screens that CV again (at most RATE_LIMIT_TRIES times).

SCREENING_MODE=manual (tests): nothing starts by itself; the endpoint calls screen_waiting() and waits for it.
The progress is kept in memory: after a restart it starts again from what still waits.
"""
import logging
import queue
import threading
import time
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core import config
from app.core.database import engine
from app.features.jobs.models import Job
from app.features.screening.services.screening_service import final_status, screen_candidate, waiting_candidates

log = logging.getLogger("screening_worker")

RATE_LIMIT_TRIES = 3
_jobs: queue.Queue = queue.Queue()
_thread_lock = threading.Lock()
_thread: threading.Thread | None = None
_progress_lock = threading.Lock()
_progress: dict[int, dict] = {}          # job id -> the latest screening run of that job


# Makes a fresh progress record for a new screening run (all counts at 0)
def _empty(total: int, running: bool) -> dict:
    return {"running": running, "total": total, "done": 0, "included": 0, "excluded": 0, "needs_review": 0,
            "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None}


# Returns a copy of the latest screening progress of the job (read by the status endpoint)
def progress_of(job_id: int) -> dict:
    with _progress_lock:
        return dict(_progress.get(job_id) or {"running": False, "total": 0, "done": 0, "included": 0, "excluded": 0,
                                              "needs_review": 0, "started_at": None, "finished_at": None})


# Changes fields of the job's progress record, safely under the progress lock
def _update(job_id: int, **changes) -> None:
    with _progress_lock:
        _progress.setdefault(job_id, _empty(0, False)).update(changes)


def start_screening(job_id: int) -> int:
    """Puts the job in the queue of the background thread. Returns how many CVs wait (for the "started" message)."""
    global _thread
    if config.SCREENING_MODE != "background":
        return 0
    with Session(engine) as session:
        job = session.get(Job, job_id)
        waiting = len(waiting_candidates(session, job)) if job and job.status == "approved" else 0
    if not waiting:
        return 0
    with _progress_lock:
        current = _progress.get(job_id)
        if current and current["running"]:                       # already running: the new CVs join this run
            current["total"] = current["done"] + waiting
        else:
            _progress[job_id] = _empty(waiting, True)
    _jobs.put(job_id)  # → puts the job in the queue; the background thread (_work) screens it
    with _thread_lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_work, name="screening-worker", daemon=True)
            _thread.start()
    return waiting


# Checks if a result failed only because the free Gemini quota said "too many requests"
def _rate_limited(result) -> bool:
    return result.result == "needs_review" and "too many requests" in (result.reason or "").lower()


def screen_waiting(job_id: int) -> dict:
    """Screens every CV of the job that waits, one after another, and returns the progress at the end.
    CVs that arrive while it runs are screened in the same run."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job or job.status != "approved":
            return progress_of(job_id)
        waiting = waiting_candidates(session, job)
        if not waiting and not progress_of(job_id)["running"]:   # nothing to do: keep the last summary
            return progress_of(job_id)
        if not progress_of(job_id)["running"]:
            with _progress_lock:
                _progress[job_id] = _empty(len(waiting), True)
        while waiting:
            candidate = waiting[0]
            # → screen_candidate runs the LangGraph screening workflow for this CV
            result = screen_candidate(session, candidate, job)
            tries = 1
            while _rate_limited(result) and tries < RATE_LIMIT_TRIES:
                log.info("free AI quota busy: waiting %ss, then candidate=%s again", config.SCREENING_RATE_LIMIT_WAIT,
                         candidate.id)
                time.sleep(config.SCREENING_RATE_LIMIT_WAIT)
                result = screen_candidate(session, candidate, job)
                tries += 1
            status = final_status(result)
            waiting = waiting_candidates(session, job)                # new uploads join; deleted ones drop out
            with _progress_lock:
                run = _progress[job_id]
                run["done"] += 1
                run[status] += 1
                run["total"] = run["done"] + len(waiting)
    _update(job_id, running=False, finished_at=datetime.now(timezone.utc).isoformat())
    run = progress_of(job_id)
    log.info("screening finished job=%s done=%d included=%d excluded=%d needs_review=%d", job_id, run["done"],
             run["included"], run["excluded"], run["needs_review"])
    return run


# Runs in the background thread: takes job ids from the queue and calls screen_waiting for each
def _work() -> None:
    while True:
        job_id = _jobs.get()
        try:
            screen_waiting(job_id)
        except Exception:
            log.exception("background screening of job %s stopped", job_id)
            _update(job_id, running=False, finished_at=datetime.now(timezone.utc).isoformat())
        finally:
            _jobs.task_done()


def resume_waiting_screening() -> None:
    """After a restart: every approved job with CVs that still wait goes into the queue."""
    with Session(engine) as session:
        job_ids = [job.id for job in session.exec(select(Job).where(Job.status == "approved")).all()
                   if waiting_candidates(session, job)]
    for job_id in job_ids:
        start_screening(job_id)
