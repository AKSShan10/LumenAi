"""LumenAI API - the FastAPI application. Open http://localhost:8010/docs (API_PORT in .env) to try every endpoint.

Folder guide (app/):
    core/       settings, database connection, login tokens, list of all tables
    ai/         talking to the AI model
    graphs/     LangGraph AI workflows
    features/   one folder per feature, each with models, schemas, routers and services
    utils/      small shared helpers
"""
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core import config
from app.core.database import init_db
from app.core.logging_setup import setup_logging
from app.graphs.checkpointer import checkpointer
from app.features.assessments.routers import assessment_router
from app.features.assessments.services.assessment_service import resume_running as resume_running_assessments
from app.features.assistant.routers import assistant_router
from app.features.auth.routers import auth_router
from app.features.candidates.routers import candidate_router
from app.features.claims.routers import claim_router
from app.features.claims.services.claim_service import resume_running as resume_running_claims
from app.features.interview_helper.routers import helper_router
from app.features.interviews.routers import interview_router, join_router
from app.features.job_library.routers import company_document_router
from app.features.jobs.routers import job_posting_router, job_router
from app.features.qa_analysis.routers import qa_analysis_router
from app.features.qa_analysis.services.qa_analysis_service import resume_running as resume_running_analyses
from app.features.screening.routers import screening_router
from app.features.screening.services.screening_worker import resume_waiting_screening
from app.features.system.routers import system_router
from app.features.talent_pool.routers import talent_pool_router, unsubscribe_router
from app.features.transcripts.routers import stt_router, transcript_router

# Logs contain ids and events only, never names or CV text. They go to the terminal and to a log file.
setup_logging(config.LOG_FILE)
log = logging.getLogger("app")
api_log = logging.getLogger("api")               # one line for every API call


# Each feature that runs long AI work adds its "resume" function here.
RESUME_FUNCTIONS: list = [resume_waiting_screening,      # CVs that still wait for screening after a restart
                          resume_running_analyses,       # Q&A analyses that were still running
                          resume_running_assessments,    # assessments that were still running
                          resume_running_claims]         # CV claim checks that were still running


def resume_unfinished_work() -> None:
    """Work that was still running when the app stopped continues after a restart.
    Finished work is saved step by step, so it is never done twice."""
    for resume in RESUME_FUNCTIONS:
        try:
            resume()
        except Exception:
            log.exception("could not resume %s", resume.__name__)


# Runs when the app starts: applies migrations, sets up the checkpointer, resumes unfinished screening
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                                    # apply the database migrations that are still missing
    checkpointer()                               # LangGraph's tables for paused workflows, made before any other work
    threading.Thread(target=resume_unfinished_work, daemon=True).start()
    yield


app = FastAPI(title=config.APP_NAME, version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_api_call(request: Request, call_next):
    """Writes one log line for every API call: what was called, how it ended and how long it took.
    Only the path is logged: never the text after "?", and never what was sent."""
    started = time.time()
    status = 500                                  # stays 500 if the request stops with an unexpected error
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        api_log.info("%s %s %s %dms", request.method, request.url.path, status, (time.time() - started) * 1000)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Never send stack traces or file paths to the browser."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


# GET /api/health: returns ok, the app name and which AI provider is used
@app.get("/api/health", tags=["System"])
def health():
    return {"status": "ok", "app_name": config.APP_NAME, "llm": config.LLM_PROVIDER}


# Each feature adds its router to this list.
for module in (auth_router,                      # login
               job_router,                       # the saved jobs (read and delete)
               job_posting_router,               # the posts of a job, and the posting check
               candidate_router,                 # CVs: fetch from the Google Form, manual upload, the saved files
               screening_router,                 # CV screening: the AI reads each CV, code checks the requirements
               interview_router,                 # interviews: schedule a shortlisted candidate, invitation email + calendar
               join_router,                      # the candidate's page (public, only with the private link)
               stt_router,                       # the live transcript: each browser sends its own microphone
               transcript_router,                # reading the transcript and the .txt download
               helper_router,                    # the AI helper in the call: suggested questions, model answers, chat
               qa_analysis_router,               # after the call: the graded answers (F5) and the interview scorecard (F9)
               assessment_router,                # the final report, the decision and the comparison (F6)
               claim_router,                     # CV claims compared with the interview: prompts for follow-up (F8)
               assistant_router,                 # the chatbot: the AI chooses tools, a person confirms
               company_document_router,          # company documents the AI will look up (RAG)
               talent_pool_router,               # talent pool: keep past candidates, invite them to new jobs
               unsubscribe_router,               # the public "no more emails" link of a pool invitation
               system_router):                   # "Test AI connection", workflow run log
    app.include_router(module.router)
