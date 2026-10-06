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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core import config
from app.core.database import init_db
from app.features.auth.routers import auth_router
from app.features.job_library.routers import company_document_router
from app.features.jobs.routers import job_posting_router, job_router
from app.features.system.routers import system_router

# Logs contain ids and events only, never names or CV text
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


# Each feature that runs long AI work adds its "resume" function here.
RESUME_FUNCTIONS: list = []


def resume_unfinished_work() -> None:
    """Work that was still running when the app stopped continues after a restart.
    Finished work is saved step by step, so it is never done twice."""
    for resume in RESUME_FUNCTIONS:
        try:
            resume()
        except Exception:
            log.exception("could not resume %s", resume.__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                                    # apply the database migrations that are still missing
    threading.Thread(target=resume_unfinished_work, daemon=True).start()
    yield


app = FastAPI(title=config.APP_NAME, version="1.0.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Never send stack traces or file paths to the browser."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


@app.get("/api/health", tags=["System"])
def health():
    return {"status": "ok", "app_name": config.APP_NAME, "llm": config.LLM_PROVIDER}


# Each feature adds its router to this list.
for module in (auth_router,                      # login
               job_router,                       # job profiles and the AI job description
               job_posting_router,               # posting an approved job to Telegram
               company_document_router,          # company documents the AI will look up (RAG)
               system_router):                   # "Test AI connection", workflow run log
    app.include_router(module.router)
